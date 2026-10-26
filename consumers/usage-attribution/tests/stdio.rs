//! Authored executable tests only; not an AppServer/Core transport test.
//! Pipe writes and wait_with_output are blocking: the test command requires an
//! outer deadline. This helper does not provide bounded subprocess settlement.
use proteus_contracts::domain::{ExchangeId, SessionUsageSnapshot};
use proteus_example_usage_attribution::{MAX_INPUT_BYTES, MAX_MODEL_BYTES, MAX_REQUESTS};
use std::{
    io::Write,
    process::{Command, Output, Stdio},
};

const FIXTURE: &[u8] = include_bytes!("../fixtures/mixed-snapshot.json");
fn run(input: &[u8]) -> Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_usage-attribution-stdin"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(input).unwrap();
    child.wait_with_output().unwrap()
}
fn failure(output: Output, diagnostic: &str) {
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty(), "no partial success report");
    assert_eq!(
        String::from_utf8(output.stderr).unwrap(),
        format!("{diagnostic}\n")
    );
}

#[test]
fn stdin_fixture_matches_exact_expected_report() {
    let output = run(FIXTURE);
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&output.stdout).unwrap(),
        serde_json::from_slice::<serde_json::Value>(include_bytes!(
            "../fixtures/expected-report.json"
        ))
        .unwrap()
    );
}
#[test]
fn stdin_null_is_unavailable_not_empty_summary() {
    let output = run(b"null");
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    assert_eq!(output.stdout, b"{\"availability\":\"unavailable\",\"schema_version\":1,\"reason\":\"snapshot_not_available\"}\n");
}
#[test]
fn stdin_invalid_payload_has_exact_diagnostic_no_report() {
    failure(
        run(b"{\"private\":\"DO_NOT_ECHO\"}"),
        "invalid usage snapshot payload",
    );
}
#[test]
fn stdin_limit_has_exact_diagnostic_no_report() {
    let mut input = b"null".to_vec();
    input.resize(MAX_INPUT_BYTES + 1, b' ');
    failure(run(&input), "input exceeds byte limit");
}
#[test]
fn arguments_are_rejected_without_opening_paths() {
    let output = Command::new(env!("CARGO_BIN_EXE_usage-attribution-stdin"))
        .arg("unused-path-not-opened")
        .stdin(Stdio::null())
        .output()
        .unwrap();
    failure(output, "this example accepts stdin only; no arguments");
}
#[test]
fn oversized_output_is_refused_before_stdout() {
    let mut s: SessionUsageSnapshot = serde_json::from_slice(FIXTURE).unwrap();
    let template = s.requests[0].clone();
    s.requests = (0..MAX_REQUESTS)
        .map(|n| {
            let mut row = template.clone();
            row.exchange_id = ExchangeId::from_u128(n as u128);
            row.model.provider = "p".repeat(MAX_MODEL_BYTES);
            row.model.model = format!("{n:04}{}", "m".repeat(MAX_MODEL_BYTES - 4));
            row
        })
        .collect();
    let input = serde_json::to_vec(&s).unwrap();
    assert!(input.len() < MAX_INPUT_BYTES);
    failure(run(&input), "output exceeds byte limit");
}
