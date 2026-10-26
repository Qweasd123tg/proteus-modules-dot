use std::{
    collections::{BTreeMap, BTreeSet},
    io::{self, Write},
    path::Path,
};

use anyhow::{Result, ensure};
use serde_json::Value;

use crate::*;

fn valid_call_id(value: &str) -> bool {
    !value.is_empty() && value.len() <= 256 && !value.chars().any(char::is_control)
}

pub fn validate_expected(policy: &ExpectedPolicy) -> Result<()> {
    ensure!(
        valid_id(&policy.expected_suite_id),
        "invalid expected suite id"
    );
    ensure!(
        valid_hash(&policy.expected_config_sha256),
        "invalid expected config digest"
    );
    ensure!(
        (1..=MAX_DOCUMENTS).contains(&policy.documents.len()),
        "expected policy needs 1..={MAX_DOCUMENTS} documents"
    );
    let mut docs = BTreeSet::new();
    let mut paths = BTreeSet::new();
    let mut count = 0usize;
    for document in &policy.documents {
        ensure!(
            valid_id(&document.document_id) && docs.insert(&document.document_id),
            "invalid or duplicate expected document"
        );
        ensure!(
            valid_path(&document.path) && paths.insert(&document.path),
            "invalid or duplicate expected path"
        );
        ensure!(
            !document.assertions.is_empty(),
            "expected document has zero assertions"
        );
        count += document.assertions.len();
        ensure!(
            count <= MAX_ASSERTIONS,
            "expected assertion count exceeds {MAX_ASSERTIONS}"
        );
        let mut assertions = BTreeSet::new();
        for assertion in &document.assertions {
            ensure!(
                valid_id(&assertion.assertion_id) && assertions.insert(&assertion.assertion_id),
                "invalid or duplicate expected assertion"
            );
            ensure!(
                valid_pointer(&assertion.pointer),
                "invalid expected pointer"
            );
        }
    }
    Ok(())
}

/// This examines an already-parsed, borrowed Value before cloning/deserializing.
/// It does not claim to bound SDK allocations or protect against a dishonest host.
fn preflight(value: &Value) -> Result<()> {
    let mut pending = vec![(value, 0usize)];
    let mut nodes = 0usize;
    while let Some((value, depth)) = pending.pop() {
        nodes += 1;
        ensure!(nodes <= 4096 && depth <= 8, "receipt shape bound exceeded");
        match value {
            Value::String(text) => ensure!(text.len() <= 8192, "receipt string bound exceeded"),
            Value::Array(values) => {
                ensure!(
                    values.len() <= MAX_ASSERTIONS,
                    "receipt array bound exceeded"
                );
                pending.extend(values.iter().map(|value| (value, depth + 1)));
            }
            Value::Object(values) => {
                ensure!(values.len() <= 16, "receipt object bound exceeded");
                for (key, value) in values {
                    ensure!(key.len() <= 64, "receipt key bound exceeded");
                    pending.push((value, depth + 1));
                }
            }
            _ => {}
        }
    }
    struct Counter(usize);
    impl Write for Counter {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            if bytes.len() > MAX_RECEIPT_BYTES.saturating_sub(self.0) {
                return Err(io::Error::other("receipt byte bound exceeded"));
            }
            self.0 += bytes.len();
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }
    serde_json::to_writer(Counter(0), value)?;
    Ok(())
}

pub fn verify_receipt(
    value: &Value,
    policy: &ExpectedPolicy,
    cwd: &Path,
    call_id: &str,
) -> Result<()> {
    validate_expected(policy)?;
    preflight(value)?;
    let receipt: Receipt = serde_json::from_value(value.clone())?;
    ensure!(
        receipt.schema_version == 2 && receipt.status == "passed" && receipt.kind == KIND,
        "wrong receipt version/status/kind"
    );
    ensure!(
        valid_call_id(&receipt.verifier_call_id) && receipt.verifier_call_id == call_id,
        "receipt verifier call id mismatch"
    );
    ensure!(
        cwd.is_absolute()
            && receipt.cwd.len() <= 4096
            && Some(receipt.cwd.as_str()) == cwd.to_str(),
        "receipt cwd mismatch"
    );
    ensure!(
        receipt.suite_id == policy.expected_suite_id,
        "receipt suite mismatch"
    );
    ensure!(
        receipt.config_sha256 == policy.expected_config_sha256,
        "receipt config digest mismatch"
    );
    ensure!(
        receipt.documents.len() == policy.documents.len(),
        "receipt document coverage mismatch"
    );
    let expected: BTreeMap<_, _> = policy
        .documents
        .iter()
        .map(|document| (&document.document_id, document))
        .collect();
    let mut seen_documents = BTreeSet::new();
    let mut seen_paths = BTreeSet::new();
    let mut reader_calls = BTreeSet::new();
    let mut total_bytes = 0usize;
    let mut total_assertions = 0usize;
    for document in &receipt.documents {
        ensure!(
            seen_documents.insert(&document.document_id),
            "duplicate receipt document"
        );
        let expected = expected
            .get(&document.document_id)
            .ok_or_else(|| anyhow::anyhow!("unexpected receipt document"))?;
        ensure!(
            document.configured_path == expected.path
                && seen_paths.insert(&document.configured_path),
            "receipt path mismatch or duplicate"
        );
        ensure!(
            Some(document.observed_path.as_str()) == cwd.join(&expected.path).to_str(),
            "receipt observed path mismatch"
        );
        ensure!(
            valid_call_id(&document.reader_call_id)
                && document.reader_call_id != receipt.verifier_call_id
                && reader_calls.insert(&document.reader_call_id),
            "invalid or duplicate reader call id"
        );
        ensure!(
            valid_hash(&document.content_sha256),
            "invalid content digest"
        );
        ensure!(
            (1..=MAX_FILE_BYTES).contains(&document.bytes),
            "invalid document byte count"
        );
        total_bytes += document.bytes;
        ensure!(
            total_bytes <= MAX_TOTAL_BYTES,
            "total byte count exceeds bound"
        );
        ensure!(
            document.assertions_executed.len() == expected.assertions.len(),
            "receipt assertion coverage mismatch"
        );
        total_assertions += document.assertions_executed.len();
        ensure!(
            total_assertions <= MAX_ASSERTIONS,
            "receipt total assertion bound exceeded"
        );
        let expected_assertions: BTreeMap<_, _> = expected
            .assertions
            .iter()
            .map(|assertion| (&assertion.assertion_id, &assertion.pointer))
            .collect();
        let mut seen = BTreeSet::new();
        for assertion in &document.assertions_executed {
            ensure!(
                seen.insert(&assertion.assertion_id),
                "duplicate receipt assertion"
            );
            let pointer = expected_assertions
                .get(&assertion.assertion_id)
                .ok_or_else(|| anyhow::anyhow!("unexpected receipt assertion"))?;
            ensure!(
                &assertion.pointer == *pointer,
                "receipt assertion pointer mismatch"
            );
            ensure!(
                assertion.check_id
                    == check_id(
                        &receipt.suite_id,
                        &receipt.config_sha256,
                        &document.content_sha256,
                        &document.document_id,
                        &assertion.assertion_id
                    ),
                "receipt check id binding mismatch"
            );
        }
    }
    ensure!(total_assertions > 0, "zero receipt assertions");
    Ok(())
}
