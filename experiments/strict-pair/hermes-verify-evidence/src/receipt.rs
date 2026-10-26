use std::path::{Path, PathBuf};

use anyhow::Result;
use proteus_example_json_receipt::{ExpectedPolicy, validate_expected, verify_receipt};
use proteus_module_sdk::contracts::domain::ToolResult;
use serde::Deserialize;
use serde_json::json;

use crate::RECEIPT_KEY;

/// Mode is mandatory. There is no automatic downgrade or shape detection.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "mode", rename_all = "snake_case", deny_unknown_fields)]
pub enum ReceiptPolicy {
    StrictJsonContracts {
        expected: ExpectedPolicy,
    },
    /// Explicit old v1 behavior: no expected suite/config/coverage enforcement.
    AdvisoryV1,
}

impl ReceiptPolicy {
    pub fn validate(&self) -> Result<()> {
        match self {
            Self::StrictJsonContracts { expected } => validate_expected(expected),
            Self::AdvisoryV1 => Ok(()),
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReceiptV1 {
    schema_version: u32,
    status: String,
    cwd: PathBuf,
    checks_executed: Vec<String>,
}

pub fn passed_receipt(result: &ToolResult, cwd: &Path, policy: &ReceiptPolicy) -> bool {
    if !result.ok || result.error.is_some() {
        return false;
    }
    let Some(value) = result.metadata.get(RECEIPT_KEY) else {
        return false;
    };
    match policy {
        ReceiptPolicy::StrictJsonContracts { expected } => {
            if !result.content.is_empty() {
                return false;
            }
            for flag in [
                "canceled",
                "timed_out",
                "output_truncated",
                "error_truncated",
            ] {
                if result
                    .metadata
                    .get(flag)
                    .is_some_and(|value| value != &json!(false))
                {
                    return false;
                }
            }
            verify_receipt(value, expected, cwd, &result.call_id).is_ok()
        }
        ReceiptPolicy::AdvisoryV1 => {
            let Ok(receipt) = serde_json::from_value::<ReceiptV1>(value.clone()) else {
                return false;
            };
            receipt.schema_version == 1
                && receipt.status == "passed"
                && receipt.cwd == cwd
                && !receipt.checks_executed.is_empty()
                && receipt.checks_executed.len() <= 256
                && receipt
                    .checks_executed
                    .iter()
                    .all(|check| !check.trim().is_empty() && check.len() <= 1024)
        }
    }
}
