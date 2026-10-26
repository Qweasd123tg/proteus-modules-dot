use std::collections::BTreeSet;

use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const MAX_CONFIG_BYTES: usize = 64 * 1024;
pub const MAX_FILE_BYTES: usize = 64 * 1024;
pub const MAX_TOTAL_BYTES: usize = 256 * 1024;
pub const MAX_CALLBACK_BYTES: usize = 512 * 1024;
pub const MAX_DOCUMENTS: usize = 16;
pub const MAX_ASSERTIONS: usize = 128;
pub const MAX_DEPTH: usize = 32;

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema_version: u32,
    pub suite_id: String,
    pub documents: Vec<Document>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Document {
    pub id: String,
    pub path: String,
    pub assertions: Vec<Assertion>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Assertion {
    pub id: String,
    pub pointer: String,
    pub rule: Rule,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Rule {
    Exists,
    Type { expected: JsonType },
    Equals { expected: Value },
    NonEmpty,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum JsonType {
    Null,
    Boolean,
    Number,
    Integer,
    String,
    Array,
    Object,
}

fn valid_id(value: &str) -> bool {
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

pub fn valid_pointer(pointer: &str) -> bool {
    if pointer.len() > 512 || (!pointer.is_empty() && !pointer.starts_with('/')) {
        return false;
    }
    if pointer.split('/').count() > MAX_DEPTH + 1 {
        return false;
    }
    let mut bytes = pointer.bytes();
    while let Some(byte) = bytes.next() {
        if byte == b'~' && !matches!(bytes.next(), Some(b'0' | b'1')) {
            return false;
        }
    }
    true
}

fn bounded_depth(value: &Value, depth: usize) -> bool {
    depth <= MAX_DEPTH
        && match value {
            Value::Array(items) => items.iter().all(|item| bounded_depth(item, depth + 1)),
            Value::Object(items) => items.values().all(|item| bounded_depth(item, depth + 1)),
            _ => true,
        }
}

// serde_json represents decimal/exponent numbers as f64. Equality evidence must
// not silently equate distinct decimals rounded to the same binary float.
fn exact_equality_domain(value: &Value) -> bool {
    match value {
        Value::Number(value) => value.is_i64() || value.is_u64(),
        Value::Array(items) => items.iter().all(exact_equality_domain),
        Value::Object(items) => items.values().all(exact_equality_domain),
        _ => true,
    }
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(self.schema_version == 1, "config schema_version must be 1");
        ensure!(valid_id(&self.suite_id), "invalid suite_id");
        ensure!(
            (1..=MAX_DOCUMENTS).contains(&self.documents.len()),
            "need 1..={MAX_DOCUMENTS} documents"
        );
        ensure!(
            serde_json::to_vec(self)?.len() <= MAX_CONFIG_BYTES,
            "config byte limit exceeded"
        );
        let mut document_ids = BTreeSet::new();
        let mut paths = BTreeSet::new();
        let mut count = 0usize;
        for document in &self.documents {
            ensure!(
                valid_id(&document.id) && document_ids.insert(&document.id),
                "invalid or duplicate document id"
            );
            ensure!(
                valid_path(&document.path) && paths.insert(&document.path),
                "invalid or duplicate document path"
            );
            ensure!(
                !document.assertions.is_empty(),
                "document has zero assertions"
            );
            count += document.assertions.len();
            ensure!(
                count <= MAX_ASSERTIONS,
                "at most {MAX_ASSERTIONS} assertions"
            );
            let mut ids = BTreeSet::new();
            for assertion in &document.assertions {
                ensure!(
                    valid_id(&assertion.id) && ids.insert(&assertion.id),
                    "invalid or duplicate assertion id"
                );
                ensure!(valid_pointer(&assertion.pointer), "invalid JSON Pointer");
                if let Rule::Equals { expected } = &assertion.rule {
                    ensure!(
                        bounded_depth(expected, 0),
                        "expected value depth limit exceeded"
                    );
                    ensure!(
                        exact_equality_domain(expected),
                        "equals expected values cannot contain decimal/exponent or out-of-range numbers; use exact integer/string values"
                    );
                }
            }
        }
        Ok(())
    }
}

impl Rule {
    pub fn matches(&self, value: Option<&Value>) -> bool {
        let Some(value) = value else { return false };
        match self {
            Self::Exists => true,
            Self::Equals { expected } => {
                exact_equality_domain(value) && exact_equality_domain(expected) && value == expected
            }
            Self::NonEmpty => match value {
                Value::String(value) => !value.is_empty(),
                Value::Array(value) => !value.is_empty(),
                Value::Object(value) => !value.is_empty(),
                _ => false,
            },
            Self::Type { expected } => match expected {
                JsonType::Null => value.is_null(),
                JsonType::Boolean => value.is_boolean(),
                JsonType::Number => value.is_number(),
                JsonType::Integer => value.is_i64() || value.is_u64(),
                JsonType::String => value.is_string(),
                JsonType::Array => value.is_array(),
                JsonType::Object => value.is_object(),
            },
        }
    }
}
