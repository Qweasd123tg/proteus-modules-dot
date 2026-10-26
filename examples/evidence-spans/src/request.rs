use std::collections::BTreeSet;

use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};

use crate::config::{MAX_CLAIMS, MAX_QUOTE_BYTES, MAX_TOTAL_QUOTE_BYTES, valid_id};

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub source_id: String,
    pub expected_sha256: String,
    pub claims: Vec<Claim>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Claim {
    pub claim_id: String,
    pub start_byte: u64,
    pub end_byte: u64,
    pub quote: String,
}

impl Request {
    pub fn validate(&self) -> Result<()> {
        ensure!(valid_id(&self.source_id), "invalid source_id");
        ensure!(
            self.expected_sha256.len() == 64
                && self
                    .expected_sha256
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "expected_sha256 must be 64 lowercase hexadecimal characters"
        );
        ensure!(
            (1..=MAX_CLAIMS).contains(&self.claims.len()),
            "invalid claim count"
        );
        let mut ids = BTreeSet::new();
        let mut total = 0usize;
        for claim in &self.claims {
            ensure!(
                valid_id(&claim.claim_id) && ids.insert(&claim.claim_id),
                "invalid or duplicate claim_id"
            );
            ensure!(
                claim.start_byte < claim.end_byte,
                "claim span must be nonempty and increasing"
            );
            ensure!(
                claim.end_byte <= crate::config::MAX_FILE_BYTES as u64,
                "claim offset exceeds source byte bound"
            );
            ensure!(
                (1..=MAX_QUOTE_BYTES).contains(&claim.quote.len()),
                "quote byte bound exceeded"
            );
            ensure!(
                claim.end_byte - claim.start_byte == claim.quote.len() as u64,
                "span length differs from quote bytes"
            );
            total = total
                .checked_add(claim.quote.len())
                .ok_or_else(|| anyhow::anyhow!("quote byte count overflow"))?;
            ensure!(
                total <= MAX_TOTAL_QUOTE_BYTES,
                "aggregate quote byte bound exceeded"
            );
        }
        Ok(())
    }
}
