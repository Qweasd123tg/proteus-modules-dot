use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct VerifiedClaim {
    pub claim_id: String,
    pub start_byte: u64,
    pub end_byte: u64,
    pub quote_sha256: String,
}

#[derive(Debug, Serialize)]
pub struct Evidence {
    pub schema_version: u32,
    pub status: &'static str,
    pub scope: &'static str,
    pub source_id: String,
    pub configured_path: String,
    pub observed_path: String,
    pub config_sha256: String,
    pub content_sha256: String,
    pub source_bytes: usize,
    pub verifier_call_id: String,
    pub reader_call_id: String,
    pub verified_claims: Vec<VerifiedClaim>,
    pub origin_verified: bool,
    pub semantic_entailment: &'static str,
}
