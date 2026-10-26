//! A consumer of a host-invoked spans verifier, not a validator of caller receipts.
use crate::{
    config::*,
    types::EvidenceRequest,
    util::{canonical, sha256},
};
use anyhow::{Result, ensure};
use proteus_module_sdk::contracts::{
    domain::{ToolCall, ToolResult, new_call_id},
    process_module::ToolModuleHost,
};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::Path};
pub const EVIDENCE_KEY: &str = "proteus.example.evidence_spans";
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VerifiedClaim {
    pub claim_id: String,
    pub start_byte: u64,
    pub end_byte: u64,
    pub quote_sha256: String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Observation {
    pub schema_version: u32,
    pub status: String,
    pub scope: String,
    pub source_id: String,
    pub configured_path: String,
    pub observed_path: String,
    pub config_sha256: String,
    pub content_sha256: String,
    pub source_bytes: u64,
    pub verifier_call_id: String,
    pub reader_call_id: String,
    pub verified_claims: Vec<VerifiedClaim>,
    pub origin_verified: bool,
    pub semantic_entailment: String,
}
pub fn check_cancel(host: &dyn ToolModuleHost) -> Result<()> {
    ensure!(
        !host
            .is_cancelled()
            .map_err(|_| anyhow::anyhow!("cancel_service_error"))?,
        "canceled"
    );
    Ok(())
}
pub fn verify(
    config: &Config,
    cwd: &Path,
    request: &EvidenceRequest,
    outer_call_id: &str,
    host: &dyn ToolModuleHost,
) -> Result<Observation> {
    request.validate(config)?;
    check_cancel(host)?;
    let call = ToolCall::new(new_call_id(), VERIFIER, serde_json::to_value(request)?);
    ensure!(call.id != outer_call_id, "nested_call_id_collision");
    let raw = host
        .execute_tool_json(serde_json::to_string(&call)?)
        .map_err(|_| anyhow::anyhow!("verifier_callback_error"))?;
    check_cancel(host)?;
    validate(config, cwd, request, &call.id, &raw)
}
pub fn validate(
    config: &Config,
    cwd: &Path,
    request: &EvidenceRequest,
    current_call_id: &str,
    raw: &str,
) -> Result<Observation> {
    ensure!(raw.len() <= MAX_CALLBACK, "verifier_response_size");
    let value = crate::strict_json::parse(raw).map_err(|_| anyhow::anyhow!("verifier_json"))?;
    let result: ToolResult =
        serde_json::from_value(value).map_err(|_| anyhow::anyhow!("verifier_result_shape"))?;
    ensure!(
        call_id(current_call_id) && result.call_id == current_call_id,
        "verifier_result_call_id"
    );
    ensure!(result.ok && result.error.is_none(), "verifier_failed");
    ensure!(result.content.is_empty(), "verifier_structured_content");
    ensure!(result.output.len() <= 4096, "verifier_output_size");
    let metadata = result
        .metadata
        .as_object()
        .ok_or_else(|| anyhow::anyhow!("verifier_metadata"))?;
    for (key, value) in metadata {
        match key.as_str() {
            EVIDENCE_KEY => {}
            "duration_ms" => ensure!(value.as_u64().is_some(), "verifier_duration"),
            "output_truncated" | "error_truncated" | "canceled" | "timed_out" => {
                ensure!(value.as_bool() == Some(false), "verifier_flag")
            }
            _ => anyhow::bail!("verifier_unknown_metadata"),
        }
    }
    let receipt = metadata
        .get(EVIDENCE_KEY)
        .ok_or_else(|| anyhow::anyhow!("verifier_missing_evidence"))?;
    canonical(receipt, MAX_OBSERVATION)?;
    let o: Observation = serde_json::from_value(receipt.clone())
        .map_err(|_| anyhow::anyhow!("verifier_evidence_shape"))?;
    validate_observation(config, cwd, request, current_call_id, &o)?;
    Ok(o)
}
/// Also used to reject corrupt stored observations. Historical IDs remain historical.
pub fn validate_observation(
    config: &Config,
    cwd: &Path,
    request: &EvidenceRequest,
    current_call_id: &str,
    o: &Observation,
) -> Result<()> {
    request.validate(config)?;
    ensure!(
        o.schema_version == 1
            && o.status == "exact_byte_match"
            && o.scope == "observed_host_read_bytes",
        "evidence_contract"
    );
    ensure!(
        call_id(current_call_id)
            && o.verifier_call_id == current_call_id
            && call_id(&o.reader_call_id)
            && o.reader_call_id != current_call_id,
        "evidence_call_id"
    );
    ensure!(
        !o.origin_verified && o.semantic_entailment == "not_evaluated",
        "evidence_scope"
    );
    let source = config.source(&request.source_id)?;
    ensure!(o.source_id == request.source_id, "evidence_source");
    ensure!(
        o.configured_path == source.path
            && Path::new(&o.observed_path) == cwd.join(&source.path)
            && o.observed_path == cwd.join(&source.path).to_str().unwrap_or(""),
        "evidence_path"
    );
    ensure!(
        hash(&o.config_sha256) && o.config_sha256 == config.evidence_policy.expected_config_sha256,
        "evidence_config_digest"
    );
    ensure!(
        hash(&o.content_sha256) && o.content_sha256 == request.expected_sha256,
        "evidence_content_digest"
    );
    ensure!(
        (1..=65536).contains(&o.source_bytes),
        "evidence_source_size"
    );
    ensure!(
        o.verified_claims.len() == request.claims.len(),
        "evidence_claim_coverage"
    );
    let expected: BTreeMap<_, _> = request.claims.iter().map(|c| (&c.claim_id, c)).collect();
    let mut seen = std::collections::BTreeSet::new();
    for got in &o.verified_claims {
        ensure!(seen.insert(&got.claim_id), "evidence_duplicate_claim");
        let want = expected
            .get(&got.claim_id)
            .ok_or_else(|| anyhow::anyhow!("evidence_claim_coverage"))?;
        ensure!(
            got.start_byte == want.start_byte
                && got.end_byte == want.end_byte
                && got.end_byte <= o.source_bytes,
            "evidence_claim_span"
        );
        ensure!(
            hash(&got.quote_sha256) && got.quote_sha256 == sha256(want.quote.as_bytes()),
            "evidence_quote_digest"
        );
    }
    canonical(o, MAX_OBSERVATION)?;
    Ok(())
}
