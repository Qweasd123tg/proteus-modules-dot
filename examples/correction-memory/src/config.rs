use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub const MAX_DEPTH: usize = 24;
pub const MAX_KEYS: usize = 256;
pub const MAX_OPERATIONS: usize = 1024;
pub const MAX_DATABASE: u64 = 16 * 1024 * 1024;
pub const MAX_PROPOSAL: usize = 32 * 1024;
pub const MAX_OBSERVATION: usize = 32 * 1024;
pub const MAX_RESPONSE: usize = 96 * 1024;
pub const MAX_CALLBACK: usize = 64 * 1024;
pub const MAX_REVISION: u64 = i64::MAX as u64;
pub const VERIFIER: &str = "evidence.verify_spans";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema_version: u32,
    pub store_id: String,
    pub database_path: String,
    pub evidence_policy: EvidencePolicy,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EvidencePolicy {
    pub verifier_tool: String,
    pub expected_config_sha256: String,
    pub sources: Vec<Source>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub source_id: String,
    pub path: String,
}
pub fn id(s: &str, max: usize) -> bool {
    !s.is_empty()
        && s.len() <= max
        && s.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_.-".contains(&c))
}
pub fn hash(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub fn relative(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 512
        && !s.contains(['\\', ':'])
        && !s.chars().any(char::is_control)
        && s.split('/').all(|p| !p.is_empty() && p != "." && p != "..")
}
pub fn call_id(s: &str) -> bool {
    !s.is_empty() && s.len() <= 128 && !s.chars().any(char::is_control)
}
impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(self.schema_version == 1, "config_version");
        ensure!(id(&self.store_id, 64), "config_store_id");
        ensure!(
            relative(&self.database_path) && self.database_path.contains('/'),
            "config_database_path"
        );
        ensure!(
            self.evidence_policy.verifier_tool == VERIFIER,
            "config_verifier"
        );
        ensure!(
            hash(&self.evidence_policy.expected_config_sha256),
            "config_verifier_digest"
        );
        ensure!(
            (1..=64).contains(&self.evidence_policy.sources.len()),
            "config_sources_count"
        );
        let (mut ids, mut paths) = (BTreeSet::new(), BTreeSet::new());
        for s in &self.evidence_policy.sources {
            ensure!(id(&s.source_id, 64) && relative(&s.path), "config_source");
            ensure!(s.path != self.database_path, "config_source_is_database");
            ensure!(
                ids.insert(&s.source_id) && paths.insert(&s.path),
                "config_duplicate_source"
            );
        }
        Ok(())
    }
    pub fn source(&self, id: &str) -> Result<&Source> {
        self.evidence_policy
            .sources
            .iter()
            .find(|s| s.source_id == id)
            .ok_or_else(|| anyhow::anyhow!("source_not_allowed"))
    }
}
