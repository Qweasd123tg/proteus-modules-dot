use std::{collections::BTreeMap, fmt};

use anyhow::{Result, ensure};
use serde::{
    Deserialize, Deserializer, Serialize,
    de::{Error, MapAccess, Visitor},
};

use crate::config::{MAX_FRONTMATTER_BYTES, valid_name};

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Frontmatter {
    pub name: String,
    pub description: String,
    pub license: Option<String>,
    pub compatibility: Option<String>,
    #[serde(default, deserialize_with = "unique_metadata")]
    pub metadata: BTreeMap<String, String>,
    #[serde(rename = "allowed-tools")]
    pub allowed_tools: Option<String>,
    #[serde(default, rename = "disable-model-invocation")]
    pub disable_model_invocation: bool,
    #[serde(rename = "user-invocable")]
    pub user_invocable: Option<bool>,
}

fn unique_metadata<'de, D: Deserializer<'de>>(d: D) -> Result<BTreeMap<String, String>, D::Error> {
    struct Unique;
    impl<'de> Visitor<'de> for Unique {
        type Value = BTreeMap<String, String>;
        fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
            f.write_str("unique string metadata keys and values")
        }
        fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
            let mut result = BTreeMap::new();
            while let Some((key, value)) = map.next_entry::<String, String>()? {
                if result.len() >= 64 {
                    return Err(A::Error::custom("at most 64 metadata keys"));
                }
                if result.insert(key, value).is_some() {
                    return Err(A::Error::custom("duplicate metadata key"));
                }
            }
            Ok(result)
        }
    }
    d.deserialize_map(Unique)
}

pub fn parse(content: &str, directory: &str) -> Result<(Frontmatter, String)> {
    let (yaml, body) = split_frontmatter(content)?;
    ensure!(
        yaml.len() <= MAX_FRONTMATTER_BYTES,
        "frontmatter exceeds 16384 bytes"
    );
    let fields: Frontmatter = serde_yaml::from_str(yaml)?;
    valid_name(&fields.name)?;
    ensure!(
        fields.name == directory,
        "frontmatter name must match directory name"
    );
    ensure!(
        !fields.description.trim().is_empty() && fields.description.chars().count() <= 1024,
        "description must be nonblank and <=1024 characters"
    );
    if let Some(value) = &fields.compatibility {
        ensure!(
            !value.trim().is_empty() && value.chars().count() <= 500,
            "compatibility must be nonblank and <=500 characters"
        );
    }
    ensure!(
        serde_json::to_vec(&fields)?.len() <= MAX_FRONTMATTER_BYTES,
        "expanded frontmatter exceeds 16384 serialized bytes"
    );
    Ok((fields, body.trim().to_owned()))
}

pub fn split_frontmatter(content: &str) -> Result<(&str, &str)> {
    let start = if content.starts_with("---\r\n") {
        5
    } else if content.starts_with("---\n") {
        4
    } else {
        anyhow::bail!("missing opening YAML marker on its own line")
    };
    let mut offset = start;
    for line in content[start..].split_inclusive('\n') {
        let unended = line.strip_suffix('\n').unwrap_or(line);
        let unended = unended.strip_suffix('\r').unwrap_or(unended);
        if unended == "---" {
            ensure!(
                offset - start <= MAX_FRONTMATTER_BYTES,
                "frontmatter exceeds 16384 bytes"
            );
            return Ok((&content[start..offset], &content[offset + line.len()..]));
        }
        offset += line.len();
        ensure!(
            offset - start <= MAX_FRONTMATTER_BYTES + 4,
            "frontmatter exceeds 16384 bytes"
        );
    }
    anyhow::bail!("missing closing YAML marker on its own line")
}

pub fn sha256(bytes: &[u8]) -> String {
    ring::digest::digest(&ring::digest::SHA256, bytes)
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
