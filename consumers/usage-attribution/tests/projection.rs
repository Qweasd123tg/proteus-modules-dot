use proteus_contracts::{
    contracts::ModelCallOrigin,
    domain::{ExchangeId, ModelUsageStatus, SessionUsageSnapshot},
    model_standard::{FinishReason, TokenUsage},
};
use proteus_example_usage_attribution::*;
use serde_json::{Value, json};

const FIXTURE: &[u8] = include_bytes!("../fixtures/mixed-snapshot.json");
fn fixture() -> SessionUsageSnapshot {
    serde_json::from_slice(FIXTURE).unwrap()
}
fn one(index: usize) -> SessionUsageSnapshot {
    let mut s = fixture();
    s.requests = vec![s.requests[index].clone()];
    assert!(summarize(&s).is_ok(), "producer-shaped baseline");
    s
}
fn error(s: &SessionUsageSnapshot, expected: &str) {
    assert_eq!(summarize(s).unwrap_err().to_string(), expected);
}

#[test]
fn mixed_fixture_matches_independent_expected_report() {
    let expected: Value =
        serde_json::from_slice(include_bytes!("../fixtures/expected-report.json")).unwrap();
    assert_eq!(
        serde_json::to_value(decode_payload(FIXTURE).unwrap()).unwrap(),
        expected
    );
}

#[test]
fn reported_zero_is_not_missing_usage() {
    let mut s = one(4);
    let zero = summarize(&s).unwrap();
    assert_eq!(zero.totals.known_total_tokens, 0);
    assert_eq!(zero.totals.usage_reported_exchanges, 1);
    assert_eq!(zero.totals.cached_input.known_sum, Some(0));
    s.requests[0].usage = None;
    let missing = summarize(&s).unwrap();
    assert_eq!(missing.totals.known_total_tokens, 0);
    assert_eq!(missing.totals.usage_missing_exchanges, 1);
    assert_eq!(missing.totals.cached_input.known_sum, None);
    assert_eq!(
        missing.groups[0].missing_usage_exchange_ids,
        vec![s.requests[0].exchange_id]
    );
}

#[test]
fn all_unknown_categories_remain_none() {
    let r = summarize(&one(2)).unwrap();
    assert_eq!(
        r.totals.cached_input,
        OptionalCategory {
            known_sum: None,
            reported_exchanges: 0,
            missing_exchanges: 1
        }
    );
    assert_eq!(r.totals.cache_creation_input, r.totals.cached_input);
    assert_eq!(r.totals.reasoning_output, r.totals.cached_input);
}

#[test]
fn repeated_model_is_two_exchanges_not_inferred_retry() {
    let mut s = one(0);
    let mut second = s.requests[0].clone();
    second.exchange_id = ExchangeId::from_u128(900);
    s.requests.push(second);
    let r = summarize(&s).unwrap();
    assert_eq!(r.recorded_model_exchanges, 2);
    assert_eq!(r.groups.len(), 1);
    assert_eq!(r.totals.known_total_tokens, 2400);
    assert_eq!(r.unavailable.retry_lineage, "not_exposed_by_snapshot");
    assert_eq!(r.unavailable.provider_attempts, "not_observed");
    assert_eq!(r.unavailable.operation_owner, "not_exposed_by_snapshot");
}

#[test]
fn provider_origin_and_status_have_distinct_groups() {
    let mut s = one(0);
    for n in 1..4 {
        let mut row = s.requests[0].clone();
        row.exchange_id = ExchangeId::from_u128(900 + n);
        match n {
            1 => row.model.provider = "other".into(),
            2 => row.origin = ModelCallOrigin::Auxiliary,
            _ => {
                row.status = ModelUsageStatus::Error;
                row.usage = None;
                row.finish_reason = None;
            }
        }
        s.requests.push(row);
    }
    let r = summarize(&s).unwrap();
    assert_eq!(r.groups.len(), 4);
    assert_eq!(r.totals.usage_reported_exchanges, 3);
    assert_eq!(r.totals.usage_missing_exchanges, 1);
}

#[test]
fn optional_denominator_includes_whole_usage_missing_rows() {
    let mut s = one(0);
    let mut second = s.requests[0].clone();
    second.exchange_id = ExchangeId::from_u128(900);
    second.usage = None;
    s.requests.push(second);
    let r = summarize(&s).unwrap();
    let c = &r.groups[0].counts;
    assert_eq!(c.exchange_count, 2);
    assert_eq!(
        c.cached_input,
        OptionalCategory {
            known_sum: Some(800),
            reported_exchanges: 1,
            missing_exchanges: 1
        }
    );
    assert_eq!(c.usage_reported_exchanges, 1);
    assert_eq!(c.usage_missing_exchanges, 1);
}

#[test]
fn large_counters_use_u64_and_do_not_double_count_subcategories() {
    let mut s = one(0);
    s.requests[0].usage = Some(
        TokenUsage::new(u32::MAX, u32::MAX)
            .with_cached_input_tokens(Some(u32::MAX))
            .with_cache_creation_input_tokens(Some(u32::MAX))
            .with_reasoning_output_tokens(Some(u32::MAX)),
    );
    let mut second = s.requests[0].clone();
    second.exchange_id = ExchangeId::from_u128(900);
    s.requests.push(second);
    let c = summarize(&s).unwrap().totals;
    assert_eq!(c.known_input_tokens, u64::from(u32::MAX) * 2);
    assert_eq!(c.known_output_tokens, u64::from(u32::MAX) * 2);
    assert_eq!(c.known_total_tokens, u64::from(u32::MAX) * 4);
    assert_eq!(c.cached_input.known_sum, Some(u64::from(u32::MAX) * 2));
}

#[test]
fn permutations_and_repeated_snapshots_do_not_accumulate() {
    let mut s = fixture();
    let first = summarize(&s).unwrap();
    s.requests.reverse();
    assert_eq!(summarize(&s).unwrap(), first);
    assert_eq!(summarize(&s).unwrap(), first);
    assert_eq!(first.session_id, s.session_id);
    assert_eq!(first.source_revision, 41);
}

#[test]
fn empty_snapshot_differs_from_unavailable_payload() {
    let mut s = fixture();
    s.requests.clear();
    let empty = summarize(&s).unwrap();
    assert_eq!(empty.recorded_model_exchanges, 0);
    assert!(empty.groups.is_empty());
    assert_eq!(
        decode_payload(b"null").unwrap(),
        PayloadReport::Unavailable {
            schema_version: 1,
            reason: "snapshot_not_available"
        }
    );
    assert_ne!(
        decode_payload(&serde_json::to_vec(&s).unwrap()).unwrap(),
        decode_payload(b"null").unwrap()
    );
}

#[test]
fn duplicate_exchange_id_is_rejected() {
    let mut s = one(0);
    s.requests.push(s.requests[0].clone());
    error(&s, "duplicate exchange id");
}
#[test]
fn completed_missing_finished_is_rejected() {
    let mut s = one(0);
    s.requests[0].finished_at_ms = None;
    error(&s, "completed exchange lacks finished_at_ms");
}
#[test]
fn completed_missing_finish_reason_is_rejected() {
    let mut s = one(0);
    s.requests[0].finish_reason = None;
    error(&s, "completed exchange lacks finish_reason");
}
#[test]
fn error_missing_finished_is_rejected() {
    let mut s = one(1);
    s.requests[0].finished_at_ms = None;
    error(&s, "error exchange lacks finished_at_ms");
}
#[test]
fn error_with_finish_reason_is_rejected() {
    let mut s = one(1);
    s.requests[0].finish_reason = Some(FinishReason::Stop);
    error(&s, "error exchange has finish_reason");
}
#[test]
fn error_with_usage_is_rejected() {
    let mut s = one(1);
    s.requests[0].usage = Some(TokenUsage::new(0, 0));
    error(&s, "error exchange has usage");
}

fn pending(status: ModelUsageStatus) -> SessionUsageSnapshot {
    let mut s = one(3);
    s.requests[0].status = status;
    assert!(summarize(&s).is_ok());
    s
}
#[test]
fn pending_with_finished_is_rejected_for_each_pending_status() {
    for status in [
        ModelUsageStatus::Unfinished,
        ModelUsageStatus::Canceled,
        ModelUsageStatus::Timeout,
    ] {
        let mut s = pending(status);
        s.requests[0].finished_at_ms = Some(1200);
        error(&s, "pending exchange has finished_at_ms");
    }
}
#[test]
fn pending_with_finish_reason_is_rejected_for_each_pending_status() {
    for status in [
        ModelUsageStatus::Unfinished,
        ModelUsageStatus::Canceled,
        ModelUsageStatus::Timeout,
    ] {
        let mut s = pending(status);
        s.requests[0].finish_reason = Some(FinishReason::Stop);
        error(&s, "pending exchange has finish_reason");
    }
}
#[test]
fn pending_with_usage_is_rejected_for_each_pending_status() {
    for status in [
        ModelUsageStatus::Unfinished,
        ModelUsageStatus::Canceled,
        ModelUsageStatus::Timeout,
    ] {
        let mut s = pending(status);
        s.requests[0].usage = Some(TokenUsage::new(0, 0));
        error(&s, "pending exchange has usage");
    }
}

#[test]
fn non_monotonic_wall_clock_does_not_become_latency() {
    let mut s = one(0);
    s.requests[0].finished_at_ms = Some(s.requests[0].started_at_ms - 1);
    let r = summarize(&s).unwrap();
    let j = serde_json::to_string(&r).unwrap();
    assert!(!j.contains("latency"));
    assert!(!j.contains("duration"));
    assert_eq!(r.totals.known_total_tokens, 1200);
}

#[test]
fn request_cap_accepts_exact_and_rejects_plus_one() {
    let mut s = one(0);
    let template = s.requests[0].clone();
    s.requests = (0..MAX_REQUESTS)
        .map(|n| {
            let mut r = template.clone();
            r.exchange_id = ExchangeId::from_u128(n as u128);
            r
        })
        .collect();
    assert_eq!(
        summarize(&s).unwrap().recorded_model_exchanges,
        MAX_REQUESTS
    );
    let mut extra = template;
    extra.exchange_id = ExchangeId::from_u128(MAX_REQUESTS as u128);
    s.requests.push(extra);
    error(&s, "request count exceeds limit");
}
#[test]
fn provider_byte_cap_accepts_exact_and_rejects_plus_one() {
    let mut s = one(0);
    s.requests[0].model.provider = "p".repeat(MAX_MODEL_BYTES);
    assert!(summarize(&s).is_ok());
    s.requests[0].model.provider.push('p');
    error(&s, "provider name exceeds byte limit");
}
#[test]
fn model_byte_cap_accepts_exact_and_rejects_plus_one() {
    let mut s = one(0);
    s.requests[0].model.model = "m".repeat(MAX_MODEL_BYTES);
    assert!(summarize(&s).is_ok());
    s.requests[0].model.model.push('m');
    error(&s, "model name exceeds byte limit");
}
#[test]
fn model_cap_counts_utf8_bytes_not_characters() {
    let mut s = one(0);
    s.requests[0].model.model = "é".repeat(MAX_MODEL_BYTES / 2);
    assert!(summarize(&s).is_ok());
    s.requests[0].model.model.push('x');
    error(&s, "model name exceeds byte limit");
}
#[test]
fn unused_request_strings_are_not_retained() {
    let mut s = one(0);
    s.requests[0].reasoning_effort = Some("PRIVATE_SENTINEL".repeat(1000));
    let output = serde_json::to_string(&summarize(&s).unwrap()).unwrap();
    assert!(!output.contains("PRIVATE_SENTINEL"));
}
#[test]
fn input_byte_cap_accepts_exact_and_rejects_plus_one() {
    let mut bytes = b"null".to_vec();
    bytes.resize(MAX_INPUT_BYTES, b' ');
    assert!(decode_payload(&bytes).is_ok());
    bytes.push(b' ');
    assert_eq!(
        decode_payload(&bytes).unwrap_err().0,
        "input exceeds byte limit"
    );
}
#[test]
fn malformed_and_unknown_field_payloads_are_rejected() {
    assert!(decode_payload(FIXTURE).is_ok());
    for bytes in [b"".as_slice(), b"{", b"[]", b"1"] {
        assert_eq!(
            decode_payload(bytes).unwrap_err().0,
            "invalid usage snapshot payload"
        );
    }
    let mut v: Value = serde_json::from_slice(FIXTURE).unwrap();
    v["invented_owner"] = json!("workflow");
    assert_eq!(
        decode_payload(&serde_json::to_vec(&v).unwrap())
            .unwrap_err()
            .0,
        "invalid usage snapshot payload"
    );
}
#[test]
fn unknown_origin_and_status_are_rejected() {
    assert!(decode_payload(FIXTURE).is_ok());
    for key in ["origin", "status"] {
        let mut v: Value = serde_json::from_slice(FIXTURE).unwrap();
        v["requests"][0][key] = json!("invented");
        assert_eq!(
            decode_payload(&serde_json::to_vec(&v).unwrap())
                .unwrap_err()
                .0,
            "invalid usage snapshot payload"
        );
    }
}
#[test]
fn response_envelope_is_not_accepted_as_payload() {
    assert!(decode_payload(FIXTURE).is_ok());
    let v: Value = serde_json::from_slice(FIXTURE).unwrap();
    assert_eq!(
        decode_payload(&serde_json::to_vec(&json!({"id":"example","result":v})).unwrap())
            .unwrap_err()
            .0,
        "invalid usage snapshot payload"
    );
}
#[test]
fn output_limit_refuses_large_bounded_report() {
    let mut s = one(0);
    let template = s.requests[0].clone();
    s.requests = (0..MAX_REQUESTS)
        .map(|n| {
            let mut r = template.clone();
            r.exchange_id = ExchangeId::from_u128(n as u128);
            r.model.provider = "p".repeat(MAX_MODEL_BYTES);
            r.model.model = format!("{n:04}{}", "m".repeat(MAX_MODEL_BYTES - 4));
            r
        })
        .collect();
    let r = PayloadReport::Available {
        report: summarize(&s).unwrap(),
    };
    assert_eq!(
        encode_report(&r).unwrap_err().0,
        "output exceeds byte limit"
    );
}
#[test]
fn unavailable_encoding_is_exact_and_not_zero_usage() {
    assert_eq!(encode_report(&decode_payload(b"null").unwrap()).unwrap(), b"{\"availability\":\"unavailable\",\"schema_version\":1,\"reason\":\"snapshot_not_available\"}\n");
}

#[test]
fn output_cap_accepts_exact_and_rejects_one_more_valid_byte() {
    fn rows(count: usize) -> SessionUsageSnapshot {
        let mut snapshot = one(0);
        let template = snapshot.requests[0].clone();
        snapshot.requests = (0..count)
            .map(|n| {
                let mut row = template.clone();
                row.exchange_id = ExchangeId::from_u128(n as u128);
                row.model.model = format!("{n:04}");
                row
            })
            .collect();
        snapshot
    }
    fn report(snapshot: &SessionUsageSnapshot) -> PayloadReport {
        PayloadReport::Available {
            report: summarize(snapshot).unwrap(),
        }
    }
    fn encoded_len(snapshot: &SessionUsageSnapshot) -> usize {
        serde_json::to_vec(&report(snapshot)).unwrap().len() + 1
    }
    // Find the largest legal row count whose minimally named groups fit.
    let mut low = 1;
    let mut high = MAX_REQUESTS;
    assert!(encoded_len(&rows(low)) < MAX_OUTPUT_BYTES);
    assert!(encoded_len(&rows(high)) > MAX_OUTPUT_BYTES);
    while low + 1 < high {
        let middle = (low + high) / 2;
        if encoded_len(&rows(middle)) <= MAX_OUTPUT_BYTES {
            low = middle;
        } else {
            high = middle;
        }
    }
    let mut snapshot = rows(low);
    let mut remaining = MAX_OUTPUT_BYTES - encoded_len(&snapshot);
    // Unescaped ASCII in each unique requested model adds exactly one JSON byte.
    for row in &mut snapshot.requests {
        let added = remaining.min(MAX_MODEL_BYTES - row.model.model.len());
        row.model.model.push_str(&"x".repeat(added));
        remaining -= added;
    }
    assert_eq!(remaining, 0);
    assert!(serde_json::to_vec(&snapshot).unwrap().len() < MAX_INPUT_BYTES);
    assert_eq!(encoded_len(&snapshot), MAX_OUTPUT_BYTES);
    assert_eq!(
        encode_report(&report(&snapshot)).unwrap().len(),
        MAX_OUTPUT_BYTES
    );
    let row = snapshot
        .requests
        .iter_mut()
        .find(|row| row.model.model.len() < MAX_MODEL_BYTES)
        .unwrap();
    row.model.model.push('x');
    assert!(serde_json::to_vec(&snapshot).unwrap().len() < MAX_INPUT_BYTES);
    assert_eq!(encoded_len(&snapshot), MAX_OUTPUT_BYTES + 1);
    assert_eq!(
        encode_report(&report(&snapshot)).unwrap_err().0,
        "output exceeds byte limit"
    );
}
