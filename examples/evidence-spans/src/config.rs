use std::collections::BTreeSet;

use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};

pub const MAX_CONFIG_BYTES: usize = 64 * 1024;
pub const MAX_SOURCES: usize = 64;
pub const MAX_FILE_BYTES: usize = 64 * 1024;
pub const MAX_CALLBACK_BYTES: usize = 512 * 1024;
pub const MAX_REQUEST_BYTES: usize = 64 * 1024;
pub const MAX_CLAIMS: usize = 32;
pub const MAX_QUOTE_BYTES: usize = 4096;
pub const MAX_TOTAL_QUOTE_BYTES: usize = 16 * 1024;
pub const MAX_RESULT_BYTES: usize = 16 * 1024;

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema_version: u32,
    pub sources: Vec<Source>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub id: String,
    pub path: String,
}

pub fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.'))
}

fn valid_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 512
        && !path.contains(['\\', ':'])
        && !path.chars().any(char::is_control)
        && path
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(self.schema_version == 1, "config schema_version must be 1");
        ensure!(
            (1..=MAX_SOURCES).contains(&self.sources.len()),
            "invalid configured source count"
        );
        ensure!(
            serde_json::to_vec(self)?.len() <= MAX_CONFIG_BYTES,
            "config byte bound exceeded"
        );
        let mut ids = BTreeSet::new();
        let mut paths = BTreeSet::new();
        for source in &self.sources {
            ensure!(
                valid_id(&source.id) && ids.insert(&source.id),
                "invalid or duplicate source id"
            );
            ensure!(
                valid_path(&source.path) && paths.insert(&source.path),
                "invalid or duplicate configured source path"
            );
        }
        Ok(())
    }
}
