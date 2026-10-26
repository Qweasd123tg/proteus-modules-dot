use std::{
    collections::BTreeSet,
    path::{Component, PathBuf},
};

use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};

pub const MAX_FILE_BYTES: usize = 131_072;
pub const MAX_FRONTMATTER_BYTES: usize = 16_384;
pub const MAX_RESPONSE_BYTES: usize = 262_144;
// Below pinned Core default output truncation threshold (200000 bytes).
pub const MAX_TOOL_OUTPUT_BYTES: usize = 131_072;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Root {
    pub id: String,
    pub path: PathBuf,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub roots: Vec<Root>,
    #[serde(default)]
    pub disabled: BTreeSet<String>,
    #[serde(default)]
    pub strict: bool,
    pub max_entries: usize,
    pub max_skills: usize,
    pub max_total_bytes: usize,
    pub max_context_bytes: usize,
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            (1..=8).contains(&self.roots.len()),
            "roots must contain 1..=8 entries"
        );
        ensure!(
            (1..=512).contains(&self.max_entries),
            "max_entries must be 1..=512"
        );
        ensure!(
            (1..=128).contains(&self.max_skills),
            "max_skills must be 1..=128"
        );
        ensure!(
            (1..=2_097_152).contains(&self.max_total_bytes),
            "max_total_bytes must be 1..=2097152"
        );
        ensure!(
            (1..=65_536).contains(&self.max_context_bytes),
            "max_context_bytes must be 1..=65536"
        );
        let mut ids = BTreeSet::new();
        let mut paths = BTreeSet::new();
        for root in &self.roots {
            ensure!(
                !root.id.is_empty()
                    && root.id.len() <= 32
                    && root
                        .id
                        .bytes()
                        .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-'),
                "root id must contain 1..=32 lowercase ASCII letters, digits or hyphens"
            );
            ensure!(ids.insert(root.id.clone()), "duplicate root id");
            ensure!(
                root.path.is_absolute()
                    && root.path.to_string_lossy().len() <= 4096
                    && !root
                        .path
                        .components()
                        .any(|c| matches!(c, Component::ParentDir)),
                "root path must be absolute, <=4096 bytes and contain no parent traversal"
            );
            let path = root
                .path
                .canonicalize()
                .unwrap_or_else(|_| root.path.clone());
            ensure!(paths.insert(path), "duplicate or aliased root path");
        }
        for id in &self.disabled {
            let (root, name) = split_id(id)?;
            ensure!(ids.contains(root), "disabled id refers to unknown root");
            valid_name(name)?;
        }
        Ok(())
    }
}

pub fn valid_name(name: &str) -> Result<()> {
    // A deliberate ASCII subset shared with the pinned native Proteus loader.
    ensure!(
        !name.is_empty()
            && name.len() <= 64
            && !name.starts_with('-')
            && !name.ends_with('-')
            && !name.contains("--")
            && name
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-'),
        "skill name must be 1..=64 lowercase ASCII letters/digits/hyphens, with no leading/trailing/consecutive hyphens"
    );
    Ok(())
}

pub fn split_id(id: &str) -> Result<(&str, &str)> {
    let (root, name) = id
        .split_once(':')
        .ok_or_else(|| anyhow::anyhow!("skill id must be root-id:skill-name"))?;
    ensure!(
        !root.is_empty() && !name.contains(':'),
        "invalid namespaced skill id"
    );
    valid_name(name)?;
    Ok((root, name))
}
