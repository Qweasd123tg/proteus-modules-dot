// Test-only probe for the actual metadata reader on clean and patched Core.
use super::*;
use crate::test_alloc::measure;
use serde_json::json;

fn with_estimates(value: Value) -> Value {
    json!({"owner":{"source":"fixture","label":"метаданные"},
        INPUT_TOKEN_ESTIMATES_METADATA_KEY: value})
}

fn id(n: usize) -> String {
    format!("f0000000-a123-4678-ab80-{n:012x}")
}

fn valid(n: usize) -> Value {
    let rows = (0..n)
        .map(|i| json!({"part_id":id(i),"tokens":i.saturating_mul(17)}))
        .collect::<Vec<_>>();
    with_estimates(json!({"parts":rows}))
}

fn legacy(metadata: &Value) -> Option<ModelInputEstimate> {
    let value = metadata.get(INPUT_TOKEN_ESTIMATES_METADATA_KEY)?;
    let estimate: ModelInputEstimate = serde_json::from_value(value.clone()).ok()?;
    let mut seen = HashSet::new();
    estimate
        .parts
        .iter()
        .all(|part| seen.insert(part.part_id))
        .then_some(estimate)
}

#[test]
fn r53_borrowed_hint_decoding_preserves_material_and_results() {
    let zero = id(0);
    let one = id(1);
    let row = || json!({"part_id":zero,"tokens":5});
    let mut snapshots = vec![];
    for (case, metadata, expected_len) in [
        ("missing", json!({"other":"preserve"}), None),
        ("scalar_metadata", json!("unrelated"), None),
        ("null_estimate", with_estimates(json!(null)), None),
        ("empty", valid(0), Some(0)),
        ("one", valid(1), Some(1)),
        ("sixteen", valid(16), Some(16)),
        ("one28", valid(128), Some(128)),
        ("one024", valid(1024), Some(1024)),
        (
            "max_tokens",
            with_estimates(json!({"parts":[{"part_id":zero,"tokens":u32::MAX}]})),
            Some(1),
        ),
        (
            "positional",
            with_estimates(json!([[[zero, 42], [one, 0]]])),
            Some(2),
        ),
        (
            "bad_uuid",
            with_estimates(json!({"parts":[{"part_id":"not-uuid","tokens":42}]})),
            None,
        ),
        (
            "duplicate",
            with_estimates(json!({"parts":[row(),row()]})),
            None,
        ),
        (
            "duplicate_uuid_spelling",
            with_estimates(
                json!({"parts":[row(),{"part_id":zero.replace("-", "").to_uppercase(),"tokens":2}]}),
            ),
            None,
        ),
        (
            "overflow",
            with_estimates(json!({"parts":[{"part_id":zero,"tokens":4294967296_u64}]})),
            None,
        ),
        (
            "negative",
            with_estimates(json!({"parts":[{"part_id":zero,"tokens":-1}]})),
            None,
        ),
        (
            "extra_row_field",
            with_estimates(
                json!({"parts":[{"part_id":one,"tokens":0,"unsupported":{"detail":"x"}}]}),
            ),
            None,
        ),
        (
            "extra_root_field",
            with_estimates(json!({"parts":[row()],"unsupported":["x","y"]})),
            None,
        ),
        (
            "missing_inner_field",
            with_estimates(json!({"parts":[{"part_id":zero}]})),
            None,
        ),
        ("missing_parts", with_estimates(json!({})), None),
    ] {
        let before = serde_json::to_vec(&metadata).unwrap();
        let (decoded, alloc) = measure(|| ModelInputEstimate::from_metadata(&metadata));
        assert_eq!(decoded, legacy(&metadata), "{case}: not previous behavior");
        assert_eq!(
            decoded.as_ref().map(|v| v.parts.len()),
            expected_len,
            "{case}"
        );
        assert_eq!(
            serde_json::to_vec(&metadata).unwrap(),
            before,
            "{case}: input changed"
        );
        println!("r53 {case}: calls={} bytes={}", alloc.calls, alloc.bytes);
        snapshots.push(json!([case, decoded]));
    }

    // Exhaustive bounded matrix, including alternate UUID encodings and row/root shapes.
    let ids = [
        json!(zero),
        json!(zero.replace("-", "")),
        json!(zero.to_uppercase()),
        json!(format!("urn:uuid:{zero}")),
        json!(format!("{{{zero}}}")),
        json!("broken"),
        json!(""),
        json!(null),
        json!(17),
        json!(vec![0; 16]),
        json!(vec![0; 15]),
        json!({"id":zero}),
    ];
    let tokens = [
        json!(0),
        json!(34),
        json!(u32::MAX),
        json!(4294967296_u64),
        json!(-1),
        json!(1.25),
        json!("0"),
        json!(null),
        json!(true),
    ];
    for id in &ids {
        for token in &tokens {
            for row in [
                json!({"part_id":id,"tokens":token}),
                json!({"part_id":id,"tokens":token,"extra":null}),
                json!([id, token]),
                json!([id, token, 0]),
            ] {
                for root in [
                    json!({"parts":[row]}),
                    json!([[row]]),
                    json!({"parts":[row],"roles":["assistant"]}),
                ] {
                    let metadata = with_estimates(root);
                    let d = ModelInputEstimate::from_metadata(&metadata);
                    assert_eq!(d, legacy(&metadata));
                    snapshots.push(json!(d));
                }
            }
        }
    }
    assert_eq!(snapshots.len(), 1315); // 19 fixed + 12 * 9 * 4 * 3
    let path = std::env::var("R53_ESTIMATE_SNAPSHOT").unwrap();
    std::fs::write(path, serde_json::to_vec(&snapshots).unwrap()).unwrap();
}
