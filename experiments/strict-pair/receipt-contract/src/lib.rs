//! Local producer/consumer convention; not an SDK or Core authority contract.
mod validate;
pub use validate::{validate_expected, verify_receipt};

use serde::{Deserialize, Serialize};

pub const RECEIPT_KEY: &str = "proteus.example.verification";
pub const KIND: &str = "json_contracts";
pub const MAX_RECEIPT_BYTES: usize = 128 * 1024;
pub const MAX_DOCUMENTS: usize = 16;
pub const MAX_ASSERTIONS: usize = 128;
pub const MAX_FILE_BYTES: usize = 64 * 1024;
pub const MAX_TOTAL_BYTES: usize = 256 * 1024;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExpectedPolicy {
    pub expected_suite_id: String,
    pub expected_config_sha256: String,
    pub documents: Vec<ExpectedDocument>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExpectedDocument {
    pub document_id: String,
    pub path: String,
    pub assertions: Vec<ExpectedAssertion>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExpectedAssertion {
    pub assertion_id: String,
    pub pointer: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub schema_version: u32,
    pub status: String,
    pub kind: String,
    pub cwd: String,
    pub verifier_call_id: String,
    pub suite_id: String,
    pub config_sha256: String,
    pub documents: Vec<DocumentEvidence>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DocumentEvidence {
    pub document_id: String,
    pub configured_path: String,
    pub observed_path: String,
    pub reader_call_id: String,
    pub content_sha256: String,
    pub bytes: usize,
    pub assertions_executed: Vec<AssertionEvidence>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AssertionEvidence {
    pub assertion_id: String,
    pub pointer: String,
    pub check_id: String,
}

pub fn check_id(
    suite: &str,
    config_hash: &str,
    content_hash: &str,
    document: &str,
    assertion: &str,
) -> String {
    format!("json:{suite}:{config_hash}:{content_hash}:{document}:{assertion}")
}

pub fn valid_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.'))
}

pub fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || matches!(b, b'a'..=b'f'))
}

pub fn valid_path(path: &str) -> bool {
    !path.is_empty()
        && path.len() <= 512
        && !path.contains(['\\', ':'])
        && !path.chars().any(char::is_control)
        && path
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

pub fn valid_pointer(pointer: &str) -> bool {
    if pointer.len() > 512
        || (!pointer.is_empty() && !pointer.starts_with('/'))
        || pointer.split('/').count() > 33
    {
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
