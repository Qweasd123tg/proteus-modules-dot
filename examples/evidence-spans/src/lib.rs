//! Exact quote witnesses over one independently host-read buffer; not source truth.
pub mod config;
mod evidence;
pub mod request;

use std::path::{Component, PathBuf};

use anyhow::{Result, bail, ensure};
use checked_read_support::checked_read;
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            ProcessComponentExportInitialize, ProcessModuleComposition, ProcessToolDefinition,
            ProcessToolInvokeInput,
        },
        domain::{ToolCall, ToolResult, ToolSafety, ToolSpec, new_call_id},
        process_module::ToolModuleHost,
    },
    tool::{ToolExport, ToolModule},
};
use ring::digest::{SHA256, digest};
use serde_json::json;

use config::{Config, MAX_CALLBACK_BYTES, MAX_FILE_BYTES, MAX_REQUEST_BYTES, MAX_RESULT_BYTES};
use evidence::{Evidence, VerifiedClaim};
use request::Request;

pub const MODULE_ID: &str = "evidence.verify_spans";
pub const TOOL_NAME: &str = MODULE_ID;
pub const EVIDENCE_KEY: &str = "proteus.example.evidence_spans";

pub fn sha256(bytes: &[u8]) -> String {
    digest(&SHA256, bytes)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn check_cancel(host: &dyn ToolModuleHost) -> Result<()> {
    ensure!(!host.is_cancelled()?, "span verification canceled");
    Ok(())
}

pub struct EvidenceSpans {
    config: Config,
    config_sha256: String,
}

impl EvidenceSpans {
    pub fn new(config: Config) -> Result<Self> {
        config.validate()?;
        let config_sha256 = sha256(&serde_json::to_vec(&config)?);
        Ok(Self {
            config,
            config_sha256,
        })
    }

    pub fn config_sha256(&self) -> &str {
        &self.config_sha256
    }

    fn verify(
        &self,
        input: &ProcessToolInvokeInput,
        host: &dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        check_cancel(host)?;
        ensure!(input.call.name == TOOL_NAME, "unexpected tool name");
        // Bound reflected host correlation data, not a security identity assertion.
        ensure!(
            !input.call.id.is_empty() && input.call.id.len() <= 128,
            "unsupported verifier call id length"
        );
        ensure!(
            serde_json::to_vec(&input.call.args)?.len() <= MAX_REQUEST_BYTES,
            "request byte bound exceeded"
        );
        let request: Request = serde_json::from_value(input.call.args.clone())
            .map_err(|_| anyhow::anyhow!("invalid evidence request"))?;
        request.validate()?;
        let source = self
            .config
            .sources
            .iter()
            .find(|source| source.id == request.source_id)
            .ok_or_else(|| anyhow::anyhow!("source_id is not operator-configured"))?;
        ensure!(input.cwd.is_absolute(), "cwd must be absolute");
        ensure!(
            !input
                .cwd
                .components()
                .any(|part| matches!(part, Component::ParentDir | Component::CurDir)),
            "cwd must be normalized"
        );
        let cwd = input
            .cwd
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("cwd must be UTF-8"))?;
        ensure!(cwd.len() <= 4096, "cwd byte bound exceeded");
        let normalized: PathBuf = input.cwd.components().collect();
        ensure!(
            normalized.as_os_str() == input.cwd.as_os_str(),
            "cwd must use canonical lexical separators/components"
        );

        check_cancel(host)?;
        let call = ToolCall::new(new_call_id(), "read_file", json!({"path":source.path}));
        let raw = host.execute_tool_json(serde_json::to_string(&call)?)?;
        check_cancel(host)?;
        ensure!(
            raw.len() <= MAX_CALLBACK_BYTES,
            "reader response byte bound exceeded"
        );
        let result: ToolResult =
            serde_json::from_str(&raw).map_err(|_| anyhow::anyhow!("invalid reader ToolResult"))?;
        let expected_path = input.cwd.join(&source.path);
        let text = checked_read(&result, &call.id, &expected_path, MAX_FILE_BYTES)?;
        check_cancel(host)?;
        let content_sha256 = sha256(text.as_bytes());
        ensure!(
            content_sha256 == request.expected_sha256,
            "source SHA256 mismatch"
        );
        let mut claims = Vec::with_capacity(request.claims.len());
        for claim in request.claims {
            check_cancel(host)?;
            let start = usize::try_from(claim.start_byte)
                .map_err(|_| anyhow::anyhow!("start offset unsupported"))?;
            let end = usize::try_from(claim.end_byte)
                .map_err(|_| anyhow::anyhow!("end offset unsupported"))?;
            ensure!(
                start < end && end <= text.len(),
                "claim span exceeds observed source"
            );
            ensure!(
                text.is_char_boundary(start) && text.is_char_boundary(end),
                "claim span splits a UTF-8 code point"
            );
            ensure!(
                text[start..end] == claim.quote,
                "claim quote does not exactly match span"
            );
            claims.push(VerifiedClaim {
                claim_id: claim.claim_id,
                start_byte: claim.start_byte,
                end_byte: claim.end_byte,
                quote_sha256: sha256(claim.quote.as_bytes()),
            });
        }
        check_cancel(host)?;
        let evidence = Evidence {
            schema_version: 1,
            status: "exact_byte_match",
            scope: "observed_host_read_bytes",
            source_id: source.id.clone(),
            configured_path: source.path.clone(),
            observed_path: expected_path
                .to_str()
                .expect("validated UTF-8 path")
                .to_owned(),
            config_sha256: self.config_sha256.clone(),
            content_sha256,
            source_bytes: text.len(),
            verifier_call_id: input.call.id.clone(),
            reader_call_id: call.id,
            verified_claims: claims,
            origin_verified: false,
            semantic_entailment: "not_evaluated",
        };
        let result = ToolResult::ok(input.call.id.clone(),
            format!("Verified {} exact quote spans in one host-read artifact. Source origin and semantic entailment were not verified.", evidence.verified_claims.len()))
            .with_metadata(json!({EVIDENCE_KEY:evidence}));
        ensure!(
            serde_json::to_vec(&result)?.len() <= MAX_RESULT_BYTES,
            "evidence result byte bound exceeded"
        );
        // A race after this poll remains Core's commit/settlement responsibility.
        check_cancel(host)?;
        Ok(result)
    }
}

impl ToolModule for EvidenceSpans {
    fn definitions(&self) -> Vec<ProcessToolDefinition> {
        vec![ProcessToolDefinition {
            spec: ToolSpec::new(TOOL_NAME,
                "Check exact SHA256 and UTF-8 byte-span quotes against one operator-configured local artifact independently read via host read_file. No network, browser, code execution or memory changes. Does not verify source origin or semantic truth.",
                json!({
                    "type":"object",
                    "properties":{
                        "source_id":{"type":"string"},
                        "expected_sha256":{"type":"string"},
                        "claims":{"type":"array","items":{
                            "type":"object","properties":{
                                "claim_id":{"type":"string"},
                                "start_byte":{"type":"integer","minimum":0},
                                "end_byte":{"type":"integer","minimum":0},
                                "quote":{"type":"string"}
                            },
                            "required":["claim_id","start_byte","end_byte","quote"],"additionalProperties":false
                        }}
                    },
                    "required":["source_id","expected_sha256","claims"],"additionalProperties":false
                }),ToolSafety::ReadOnly).with_timeout(60_000).with_parallel_tool_calls(false),
            model_visible:true, user_command:None,
        }]
    }

    fn invoke(
        &self,
        input: ProcessToolInvokeInput,
        host: &mut dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        ensure!(
            !input.call.id.is_empty() && input.call.id.len() <= 128,
            "unsupported verifier call id length"
        );
        // Refusals never carry a positive witness. Module-generated validation
        // diagnostics omit quotes; trusted host error text may be retained bounded.
        match self.verify(&input, host) {
            Ok(result) => Ok(result),
            Err(error) => {
                // Keep correlation and cooperative cancellation under the existing SDK.
                if host.is_cancelled()? {
                    bail!("span verification canceled");
                }
                let message = error.to_string();
                let bounded: String = message.chars().take(512).collect();
                Ok(ToolResult::error(input.call.id, bounded))
            }
        }
    }
}

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    ensure!(
        binding.slot == "tool"
            && binding.module_id == MODULE_ID
            && binding.composition == ProcessModuleComposition::OrderedMany,
        "unsupported export binding"
    );
    let config: Config = serde_json::from_value(binding.module_config.clone())?;
    Ok(Box::new(ToolExport::new(
        binding,
        EvidenceSpans::new(config)?,
    )?))
}
