//! Synthetic contract data. No reads or assertions are executed in this file.
use proteus_example_json_receipt::*;
use serde_json::json;
use std::path::Path;

fn fixture(documents: usize, assertions: usize) -> (ExpectedPolicy, Receipt) {
    let mut expected = ExpectedPolicy {
        expected_suite_id: "suite".into(),
        expected_config_sha256: "a".repeat(64),
        documents: vec![],
    };
    let mut receipt = Receipt {
        schema_version: 2,
        status: "passed".into(),
        kind: KIND.into(),
        cwd: "/workspace".into(),
        verifier_call_id: "v".into(),
        suite_id: "suite".into(),
        config_sha256: "a".repeat(64),
        documents: vec![],
    };
    for d in 0..documents {
        let id = format!("doc{d}");
        let path = format!("file{d}.json");
        let hash = "b".repeat(64);
        let checks: Vec<_> = (0..assertions)
            .map(|a| ExpectedAssertion {
                assertion_id: format!("check{a}"),
                pointer: format!("/value{a}"),
            })
            .collect();
        expected.documents.push(ExpectedDocument {
            document_id: id.clone(),
            path: path.clone(),
            assertions: checks.clone(),
        });
        receipt.documents.push(DocumentEvidence {
            document_id: id.clone(),
            configured_path: path.clone(),
            observed_path: format!("/workspace/{path}"),
            reader_call_id: format!("reader-{d}"),
            content_sha256: hash.clone(),
            bytes: 100,
            assertions_executed: checks
                .iter()
                .map(|a| AssertionEvidence {
                    assertion_id: a.assertion_id.clone(),
                    pointer: a.pointer.clone(),
                    check_id: check_id(
                        "suite",
                        &receipt.config_sha256,
                        &hash,
                        &id,
                        &a.assertion_id,
                    ),
                })
                .collect(),
        });
    }
    (expected, receipt)
}
fn verify(expected: &ExpectedPolicy, receipt: &Receipt) -> anyhow::Result<()> {
    verify_receipt(
        &serde_json::to_value(receipt).unwrap(),
        expected,
        Path::new("/workspace"),
        "v",
    )
}

#[test]
fn exact_document_and_assertion_bounds_then_one_over() {
    let (e, r) = fixture(MAX_DOCUMENTS, 1);
    verify(&e, &r).unwrap();
    let (e, r) = fixture(MAX_DOCUMENTS + 1, 1);
    assert!(validate_expected(&e).is_err());
    let (good, _) = fixture(MAX_DOCUMENTS, 1);
    assert!(verify(&good, &r).is_err());
    let (e, r) = fixture(1, MAX_ASSERTIONS);
    verify(&e, &r).unwrap();
    let (e, r) = fixture(1, MAX_ASSERTIONS + 1);
    assert!(validate_expected(&e).is_err());
    let (good, _) = fixture(1, MAX_ASSERTIONS);
    assert!(
        verify(&good, &r)
            .unwrap_err()
            .to_string()
            .contains("array bound")
    );
}
#[test]
fn nonempty_and_unique_expected_coverage_is_required() {
    for (d, a) in [(0, 1), (1, 0)] {
        let (e, _) = fixture(d, a);
        assert!(validate_expected(&e).is_err());
    }
    let (mut e, _) = fixture(2, 2);
    e.documents[1].path = e.documents[0].path.clone();
    assert!(validate_expected(&e).is_err());
    let (mut e, _) = fixture(1, 2);
    e.documents[0].assertions[1].assertion_id = e.documents[0].assertions[0].assertion_id.clone();
    assert!(validate_expected(&e).is_err());
}
#[test]
fn exact_per_file_and_total_byte_counts_then_one_over() {
    let (e, mut r) = fixture(4, 1);
    for d in &mut r.documents {
        d.bytes = MAX_FILE_BYTES;
    }
    verify(&e, &r).unwrap();
    r.documents[0].bytes += 1;
    assert!(
        verify(&e, &r)
            .unwrap_err()
            .to_string()
            .contains("document byte count")
    );
    let (e, mut r) = fixture(5, 1);
    for d in &mut r.documents[..4] {
        d.bytes = MAX_FILE_BYTES;
    }
    r.documents[4].bytes = 1;
    assert!(
        verify(&e, &r)
            .unwrap_err()
            .to_string()
            .contains("total byte count")
    );
    let (e, mut r) = fixture(1, 1);
    r.documents[0].bytes = 0;
    assert!(verify(&e, &r).is_err());
}
#[test]
fn shape_is_checked_before_deserialization_and_unknowns_are_not_ignored() {
    let (e, r) = fixture(1, 1);
    let mut v = serde_json::to_value(&r).unwrap();
    v["unknown"] = json!(true);
    assert!(
        verify_receipt(&v, &e, Path::new("/workspace"), "v")
            .unwrap_err()
            .to_string()
            .contains("unknown field")
    );
    let mut v = serde_json::to_value(&r).unwrap();
    v["status"] = json!("x".repeat(8193));
    assert!(
        verify_receipt(&v, &e, Path::new("/workspace"), "v")
            .unwrap_err()
            .to_string()
            .contains("string bound")
    );
    let mut v = serde_json::to_value(&r).unwrap();
    let mut deep = json!(0);
    for _ in 0..9 {
        deep = json!([deep]);
    }
    v["unknown"] = deep;
    assert!(
        verify_receipt(&v, &e, Path::new("/workspace"), "v")
            .unwrap_err()
            .to_string()
            .contains("shape bound")
    );
}
#[test]
fn byte_preflight_rejects_otherwise_structurally_valid_oversized_receipt() {
    let (mut e, mut r) = fixture(16, 8);
    let cwd = format!("/{}", "w".repeat(4095));
    r.cwd = cwd.clone();
    for (ed, rd) in e.documents.iter_mut().zip(&mut r.documents) {
        rd.observed_path = format!("{cwd}/{}", ed.path);
        for (ea, ra) in ed.assertions.iter_mut().zip(&mut rd.assertions_executed) {
            ea.pointer = format!("/{}", "x".repeat(511));
            ra.pointer = ea.pointer.clone();
        }
    }
    assert!(serde_json::to_vec(&r).unwrap().len() > MAX_RECEIPT_BYTES);
    assert!(
        verify_receipt(&serde_json::to_value(r).unwrap(), &e, Path::new(&cwd), "v")
            .unwrap_err()
            .to_string()
            .contains("receipt byte bound")
    );
}
#[test]
fn invalid_hashes_call_ids_and_unknown_versions_fail() {
    let (e, r) = fixture(1, 1);
    verify(&e, &r).unwrap();
    for hash in ["", "A", "f".repeat(63).as_str(), "g".repeat(64).as_str()] {
        let mut x = r.clone();
        x.documents[0].content_sha256 = hash.into();
        x.documents[0].assertions_executed[0].check_id = check_id(
            &x.suite_id,
            &x.config_sha256,
            hash,
            &x.documents[0].document_id,
            "check0",
        );
        assert_eq!(
            verify(&e, &x).unwrap_err().to_string(),
            "invalid content digest"
        );
    }
    for id in ["", "\n", "x".repeat(257).as_str()] {
        let mut x = r.clone();
        x.verifier_call_id = id.into();
        assert_eq!(
            verify_receipt(
                &serde_json::to_value(x).unwrap(),
                &e,
                Path::new("/workspace"),
                id
            )
            .unwrap_err()
            .to_string(),
            "receipt verifier call id mismatch"
        );
    }
    let mut max_call = r.clone();
    max_call.verifier_call_id = "x".repeat(256);
    verify_receipt(
        &serde_json::to_value(&max_call).unwrap(),
        &e,
        Path::new("/workspace"),
        &max_call.verifier_call_id,
    )
    .unwrap();
    for version in [0, 1, 3] {
        let mut x = r.clone();
        x.schema_version = version;
        assert!(verify(&e, &x).is_err());
    }
    for status in ["failed", "skipped", "canceled", ""] {
        let mut x = r.clone();
        x.status = status.into();
        assert!(verify(&e, &x).is_err());
    }
}
#[test]
fn duplicate_ids_are_rejected_even_when_lengths_match() {
    let (e, mut r) = fixture(2, 2);
    r.documents[1] = r.documents[0].clone();
    assert!(
        verify(&e, &r)
            .unwrap_err()
            .to_string()
            .contains("duplicate receipt document")
    );
    let (e, mut r) = fixture(1, 2);
    r.documents[0].assertions_executed[1] = r.documents[0].assertions_executed[0].clone();
    assert!(
        verify(&e, &r)
            .unwrap_err()
            .to_string()
            .contains("duplicate receipt assertion")
    );
}
#[test]
fn permutations_keep_exact_set_coverage() {
    let (e, mut r) = fixture(2, 3);
    r.documents.reverse();
    for d in &mut r.documents {
        d.assertions_executed.reverse();
    }
    verify(&e, &r).unwrap();
}
#[test]
fn every_identity_field_mismatch_is_independently_rejected() {
    let (e, r) = fixture(1, 1);
    let value = serde_json::to_value(r).unwrap();
    for (pointer, replacement) in [
        ("/suite_id", json!("other")),
        ("/config_sha256", json!("b".repeat(64))),
        ("/cwd", json!("/other")),
        ("/verifier_call_id", json!("other")),
        ("/documents/0/configured_path", json!("other.json")),
        ("/documents/0/observed_path", json!("/workspace/other.json")),
        (
            "/documents/0/assertions_executed/0/pointer",
            json!("/other"),
        ),
        (
            "/documents/0/assertions_executed/0/check_id",
            json!("other"),
        ),
    ] {
        let mut x = value.clone();
        *x.pointer_mut(pointer).unwrap() = replacement;
        assert!(
            verify_receipt(&x, &e, Path::new("/workspace"), "v").is_err(),
            "{pointer}"
        );
    }
}
#[test]
fn receipt_fields_do_not_expand_trust_into_authentication() {
    let (e, mut r) = fixture(1, 1);
    r.documents[0].content_sha256 = "c".repeat(64);
    r.documents[0].assertions_executed[0].check_id = check_id(
        &r.suite_id,
        &r.config_sha256,
        &r.documents[0].content_sha256,
        &r.documents[0].document_id,
        "check0",
    );
    // A consistent claim from a dishonest trusted source remains undetectable.
    // This is a documented trust limit, not a real filesystem verification.
    verify(&e, &r).unwrap();
}
