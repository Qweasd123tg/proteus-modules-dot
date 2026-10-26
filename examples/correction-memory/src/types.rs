use crate::{config::*, util::canonical};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Claim {
    pub claim_id: String,
    pub start_byte: u64,
    pub end_byte: u64,
    pub quote: String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceRequest {
    pub source_id: String,
    pub expected_sha256: String,
    pub claims: Vec<Claim>,
}
impl EvidenceRequest {
    pub fn validate(&self, config: &Config) -> Result<()> {
        config.source(&self.source_id)?;
        ensure!(hash(&self.expected_sha256), "evidence_content_digest");
        ensure!(
            (1..=32).contains(&self.claims.len()),
            "evidence_claim_count"
        );
        let mut ids = BTreeSet::new();
        let mut total = 0;
        for c in &self.claims {
            ensure!(
                id(&c.claim_id, 64) && ids.insert(&c.claim_id),
                "evidence_claim_id"
            );
            ensure!(
                !c.quote.is_empty() && c.quote.len() <= 4096,
                "evidence_quote_size"
            );
            ensure!(
                c.start_byte < c.end_byte
                    && c.end_byte <= 65536
                    && c.end_byte - c.start_byte == c.quote.len() as u64,
                "evidence_span"
            );
            total += c.quote.len();
        }
        ensure!(total <= 16384, "evidence_total_quote_size");
        Ok(())
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrepareRequest {
    pub key: String,
    pub new_text: String,
    pub evidence: EvidenceRequest,
}
impl PrepareRequest {
    pub fn validate(&self, config: &Config) -> Result<()> {
        ensure!(id(&self.key, 128), "invalid_key");
        ensure!(
            !self.new_text.trim().is_empty() && self.new_text.len() <= 4096,
            "new_text_size"
        );
        self.evidence.validate(config)
    }
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    pub schema_version: u32,
    pub store_id: String,
    pub database_instance_id: String,
    pub workspace_cwd: String,
    pub database_path: String,
    pub policy_sha256: String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Proposal {
    pub schema_version: u32,
    pub store_id: String,
    pub database_instance_id: String,
    pub workspace_cwd: String,
    pub database_path: String,
    pub policy_sha256: String,
    pub key: String,
    pub expected_revision: u64,
    pub new_text: String,
    pub evidence: EvidenceRequest,
}
impl Proposal {
    pub fn new(identity: &Identity, revision: u64, request: PrepareRequest) -> Self {
        Self {
            schema_version: identity.schema_version,
            store_id: identity.store_id.clone(),
            database_instance_id: identity.database_instance_id.clone(),
            workspace_cwd: identity.workspace_cwd.clone(),
            database_path: identity.database_path.clone(),
            policy_sha256: identity.policy_sha256.clone(),
            key: request.key,
            expected_revision: revision,
            new_text: request.new_text,
            evidence: request.evidence,
        }
    }
    pub fn identity(&self) -> Identity {
        Identity {
            schema_version: self.schema_version,
            store_id: self.store_id.clone(),
            database_instance_id: self.database_instance_id.clone(),
            workspace_cwd: self.workspace_cwd.clone(),
            database_path: self.database_path.clone(),
            policy_sha256: self.policy_sha256.clone(),
        }
    }
    pub fn validate(&self, config: &Config) -> Result<()> {
        ensure!(self.schema_version == 1, "proposal_version");
        ensure!(id(&self.store_id, 64), "proposal_store_id");
        ensure!(
            self.database_instance_id.len() == 32
                && self
                    .database_instance_id
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "proposal_instance"
        );
        ensure!(
            self.workspace_cwd.len() <= 4096 && !self.workspace_cwd.chars().any(char::is_control),
            "proposal_cwd"
        );
        ensure!(
            relative(&self.database_path) && hash(&self.policy_sha256),
            "proposal_identity"
        );
        ensure!(self.expected_revision <= MAX_REVISION, "proposal_revision");
        PrepareRequest {
            key: self.key.clone(),
            new_text: self.new_text.clone(),
            evidence: self.evidence.clone(),
        }
        .validate(config)?;
        canonical(self, MAX_PROPOSAL)?;
        Ok(())
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ApplyRequest {
    pub operation_id: String,
    pub proposal: Proposal,
}
impl ApplyRequest {
    pub fn validate(&self, config: &Config) -> Result<()> {
        ensure!(id(&self.operation_id, 64), "invalid_operation_id");
        self.proposal.validate(config)?;
        canonical(self, MAX_PROPOSAL + 128)?;
        Ok(())
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ReadRequest {
    Entry { key: String },
    Operation { operation_id: String },
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Decision {
    Applied,
    Conflict,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Outcome {
    pub schema_version: u32,
    pub store_id: String,
    pub database_instance_id: String,
    pub workspace_cwd: String,
    pub database_path: String,
    pub operation_id: String,
    pub request_sha256: String,
    pub key: String,
    pub expected_revision: u64,
    pub observed_revision: u64,
    pub decision: Decision,
    pub resulting_revision: Option<u64>,
    pub proposal_sha256: String,
    pub evidence_observation_sha256: String,
}
