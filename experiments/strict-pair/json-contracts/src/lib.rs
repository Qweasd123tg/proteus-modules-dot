//! A real bounded JSON assertion producer, never an arbitrary test runner.
pub mod config;
mod reader;
mod strict_json;

use std::path::Component;

use anyhow::{Result, bail, ensure};
use proteus_example_json_receipt::{
    AssertionEvidence, DocumentEvidence, ExpectedAssertion, ExpectedDocument, ExpectedPolicy, KIND,
    Receipt, check_id, verify_receipt,
};
use proteus_module_sdk::{
    Export,
    contracts::{
        contracts::{
            ProcessComponentExportInitialize, ProcessModuleComposition, ProcessToolDefinition,
            ProcessToolInvokeInput,
        },
        domain::{ToolCall, ToolResult, ToolSafety, ToolSpec, new_call_id},
        process_module::ToolModuleHost,
    },
    tool::{ToolExport, ToolModule},
};
use ring::digest::{SHA256, digest};
use serde_json::json;

use config::{Config, MAX_CALLBACK_BYTES, MAX_TOTAL_BYTES};

pub const MODULE_ID: &str = "verification.json_contracts";
pub const TOOL_NAME: &str = MODULE_ID;
pub use proteus_example_json_receipt::RECEIPT_KEY;
pub const AUDIT_KEY: &str = "proteus.example.json_contracts";
pub const MAX_RESULT_BYTES: usize = 128 * 1024;

pub fn sha256(bytes: &[u8]) -> String {
    digest(&SHA256, bytes)
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub struct JsonContracts {
    config: Config,
    config_sha256: String,
}

fn check_cancel(host: &dyn ToolModuleHost) -> Result<()> {
    ensure!(!host.is_cancelled()?, "JSON verification canceled");
    Ok(())
}

impl JsonContracts {
    pub fn new(config: Config) -> Result<Self> {
        config.validate()?;
        // Typed serialization is the documented fingerprint representation. Object
        // ordering follows this pinned serde_json build; this is not RFC8785/JCS.
        let config_sha256 = sha256(&serde_json::to_vec(&config)?);
        Ok(Self {
            config,
            config_sha256,
        })
    }

    pub fn config_sha256(&self) -> &str {
        &self.config_sha256
    }

    /// Operator helper: derive exact consumer expectations from this validated
    /// config. Calling this helper does not install policy or grant authority.
    pub fn expected_policy(&self) -> ExpectedPolicy {
        ExpectedPolicy {
            expected_suite_id: self.config.suite_id.clone(),
            expected_config_sha256: self.config_sha256.clone(),
            documents: self
                .config
                .documents
                .iter()
                .map(|document| ExpectedDocument {
                    document_id: document.id.clone(),
                    path: document.path.clone(),
                    assertions: document
                        .assertions
                        .iter()
                        .map(|assertion| ExpectedAssertion {
                            assertion_id: assertion.id.clone(),
                            pointer: assertion.pointer.clone(),
                        })
                        .collect(),
                })
                .collect(),
        }
    }

    fn verify(
        &self,
        input: ProcessToolInvokeInput,
        host: &dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        check_cancel(host)?;
        ensure!(input.call.name == TOOL_NAME, "unexpected tool name");
        ensure!(
            !input.call.id.is_empty()
                && input.call.id.len() <= 256
                && !input.call.id.chars().any(char::is_control),
            "invalid verifier call id"
        );
        ensure!(
            input.call.args == json!({}),
            "verification accepts only empty arguments; policy is operator-configured"
        );
        ensure!(input.cwd.is_absolute(), "cwd must be absolute");
        ensure!(
            !input
                .cwd
                .components()
                .any(|part| matches!(part, Component::ParentDir | Component::CurDir)),
            "cwd must be normalized"
        );
        let cwd = input
            .cwd
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("cwd is not UTF-8"))?;
        ensure!(cwd.len() <= 4096, "cwd is too long");
        let mut evidence = Vec::new();
        let mut check_count = 0usize;
        let mut total_bytes = 0usize;
        for document in &self.config.documents {
            check_cancel(host)?;
            // A fresh SDK-generated call ID is only correlation, not a receipt signature.
            let call = ToolCall::new(new_call_id(), "read_file", json!({"path":document.path}));
            ensure!(
                call.id != input.call.id,
                "reader/verifier call id collision"
            );
            let raw = host.execute_tool_json(serde_json::to_string(&call)?)?;
            check_cancel(host)?;
            if raw.len() > MAX_CALLBACK_BYTES {
                return Ok(ToolResult::error(
                    input.call.id,
                    "reader response exceeds local byte bound",
                ));
            }
            let result: ToolResult = match serde_json::from_str(&raw) {
                Ok(result) => result,
                Err(_) => {
                    return Ok(ToolResult::error(
                        input.call.id,
                        "reader returned invalid ToolResult",
                    ));
                }
            };
            let expected_path = input.cwd.join(&document.path);
            let text = match reader::checked_read(&result, &call.id, &expected_path) {
                Ok(text) => text,
                Err(error) => {
                    return Ok(ToolResult::error(
                        input.call.id,
                        format!("document {}: {error}", document.id),
                    ));
                }
            };
            total_bytes += text.len();
            if total_bytes > MAX_TOTAL_BYTES {
                return Ok(ToolResult::error(
                    input.call.id,
                    "total document byte bound exceeded",
                ));
            }
            let parsed = match strict_json::parse(text) {
                Ok(value) => value,
                Err(error) => {
                    return Ok(ToolResult::error(
                        input.call.id,
                        format!(
                            "document {} is not unambiguous bounded JSON: {error}",
                            document.id
                        ),
                    ));
                }
            };
            check_cancel(host)?;
            let content_sha256 = sha256(text.as_bytes());
            let mut document_checks = Vec::new();
            for assertion in &document.assertions {
                check_cancel(host)?;
                if !assertion.rule.matches(parsed.pointer(&assertion.pointer)) {
                    return Ok(ToolResult::error(
                        input.call.id,
                        format!(
                            "configured JSON assertion failed: {} / {}",
                            document.id, assertion.id
                        ),
                    ));
                }
                let check_id = check_id(
                    &self.config.suite_id,
                    &self.config_sha256,
                    &content_sha256,
                    &document.id,
                    &assertion.id,
                );
                document_checks.push(AssertionEvidence {
                    assertion_id: assertion.id.clone(),
                    pointer: assertion.pointer.clone(),
                    check_id,
                });
                check_count += 1;
            }
            evidence.push(DocumentEvidence {
                document_id: document.id.clone(),
                configured_path: document.path.clone(),
                observed_path: expected_path
                    .to_str()
                    .expect("validated UTF-8 path")
                    .to_owned(),
                reader_call_id: call.id,
                bytes: text.len(),
                content_sha256,
                assertions_executed: document_checks,
            });
        }
        check_cancel(host)?;
        ensure!(check_count > 0, "zero checks cannot produce a receipt");
        let receipt = serde_json::to_value(Receipt {
            schema_version: 2,
            status: "passed".into(),
            kind: KIND.into(),
            cwd: cwd.to_owned(),
            verifier_call_id: input.call.id.clone(),
            suite_id: self.config.suite_id.clone(),
            config_sha256: self.config_sha256.clone(),
            documents: evidence,
        })?;
        verify_receipt(
            &receipt,
            &self.expected_policy(),
            &input.cwd,
            &input.call.id,
        )?;
        let metadata = json!({
            RECEIPT_KEY: receipt,
            AUDIT_KEY: {
                "schema_version":2,
                "scope":"configured_json_assertions_over_observed_host_read_bytes",
                "attribution":input.attribution,
                "total_bytes":total_bytes,
            },
        });
        let output = format!(
            "Passed {} configured JSON assertions over {} host-read documents. This is not a code/test-suite result or an atomic filesystem snapshot.",
            check_count,
            self.config.documents.len()
        );
        let result = ToolResult::ok(input.call.id, output).with_metadata(metadata);
        ensure!(
            serde_json::to_vec(&result)?.len() <= MAX_RESULT_BYTES,
            "evidence result byte bound exceeded"
        );
        // No positive evidence leaves this method after an observed cancellation.
        // A race after this poll belongs to host commit/settlement, not this module.
        check_cancel(host)?;
        Ok(result)
    }
}

impl ToolModule for JsonContracts {
    fn definitions(&self) -> Vec<ProcessToolDefinition> {
        vec![ProcessToolDefinition {
            spec: ToolSpec::new(TOOL_NAME,
                "Verify every operator-configured JSON assertion via host read_file. Returns scoped evidence only for those observed bytes; never executes project code or arbitrary tests. Takes no policy/results/paths from the model.",
                json!({"type":"object","properties":{},"additionalProperties":false}), ToolSafety::ReadOnly)
                .with_timeout(120_000)
                .with_parallel_tool_calls(false),
            model_visible: true,
            user_command: None,
        }]
    }

    fn invoke(
        &self,
        input: ProcessToolInvokeInput,
        host: &mut dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        self.verify(input, host)
    }
}

pub fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn Export>> {
    if binding.slot != "tool"
        || binding.module_id != MODULE_ID
        || binding.composition != ProcessModuleComposition::OrderedMany
    {
        bail!("unsupported export binding");
    }
    let config: Config = serde_json::from_value(binding.module_config.clone())?;
    Ok(Box::new(ToolExport::new(
        binding,
        JsonContracts::new(config)?,
    )?))
}
