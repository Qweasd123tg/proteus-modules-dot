use serde::{Serialize, Deserialize};
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Source {
    pub url: String,
    #[serde(default)]
    pub branch: Option<String>,
}

impl Source {
    /// Stable across client builds; no dependence on Rust's hash algorithm.
    pub fn key(&self) -> String {
        key(&format!(
            "{}\n{}",
            self.url,
            self.branch.as_deref().unwrap_or_default()
        ))
    }

    /// `owner/repo` of the URL; titles a repository without an index.
    pub fn name(&self) -> String {
        let url = self.url.trim_end_matches('/');
        let url = url.strip_suffix(".git").unwrap_or(url);
        let mut parts = url
            .rsplit(['/', ':'])
            .filter(|part| !part.is_empty())
            .take(2)
            .collect::<Vec<_>>();
        parts.reverse();
        parts.join("/")
    }
}

pub fn key(text: &str) -> String {
    let hash = text.bytes().fold(0xcbf29ce484222325u64, |hash, byte| {
        (hash ^ u64::from(byte)).wrapping_mul(0x100000001b3)
    });
    format!("{hash:016x}")
}

#[path="../../../src/catalog/schema.rs"] pub mod schema;
#[path="../../../src/catalog/skills.rs"] pub mod skills;
pub mod git;
