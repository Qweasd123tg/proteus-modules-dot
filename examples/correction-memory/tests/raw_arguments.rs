//! Direct-trait normalization precondition; no Core admission claim.
mod common;
use common::*;
use proteus_example_correction_memory::{config::MAX_PROPOSAL, *};
use proteus_module_sdk::{
    contracts::{
        contracts::{ExecutionAttribution, ProcessToolInvokeInput},
        domain::{ToolCall, ToolCallSurface, ToolResult, new_execution_id},
    },
    tool::ToolModule,
};
use serde_json::{Value, json};

fn input(e: &Env, name: &str, args: Value, raw: Option<String>) -> ProcessToolInvokeInput {
    let mut call = ToolCall::new("raw-case", name, args);
    call.raw_arguments = raw;
    ProcessToolInvokeInput {
        call,
        cwd: e.cwd().into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: Default::default(),
    }
}
fn exact_failure(result: &ToolResult, error: &str) {
    fail(result, error);
    assert_eq!(result.error.as_deref(), Some(error));
}
fn no_effect(e: &Env, host: &Host) {
    assert!(!e.db().exists());
    assert_eq!(std::fs::read_dir(e.cwd().join("store")).unwrap().count(), 0);
    assert_eq!(host.count(), 0);
}
#[test]
fn normalized_raw_function_init_and_null_raw_control_both_work() {
    for raw in [None, Some(" \n{}\t ".into())] {
        let e = Env::new();
        let mut host = e.host();
        let r = e
            .module
            .invoke(input(&e, INIT, json!({}), raw), &mut host)
            .unwrap();
        assert!(r.ok, "{r:?}");
        assert!(e.db().is_file());
        assert_eq!(host.count(), 0);
    }
}
#[test]
fn inconsistent_direct_trait_arguments_refuse_before_store_resolution() {
    let e = Env::new();
    let mut host = e.host();
    let mut call = input(
        &e,
        READ,
        json!({"kind":"entry","key":"B"}),
        Some(r#"{"kind":"entry","key":"A"}"#.into()),
    );
    call.cwd = e.cwd().join("nonexistent-cwd");
    let r = e.module.invoke(call, &mut host).unwrap();
    exact_failure(
        &r,
        "correction_memory: raw_arguments_normalization_mismatch",
    );
    no_effect(&e, &host);
}
#[test]
fn duplicate_keys_reject_even_when_sdk_normalized_value_matches() {
    let prepared = serde_json::to_string(&request()).unwrap();
    let nested = prepared.replace(
        r#""quote":"channel=draft""#,
        r#""quote":"wrong","quote":"channel=draft""#,
    );
    assert_ne!(nested, prepared);
    for (name, raw) in [
        (READ, r#"{"kind":"entry","key":"B","key":"A"}"#.to_string()),
        (PREPARE, nested),
    ] {
        let e = Env::new();
        let mut host = e.host();
        let normalized: Value = serde_json::from_str(&raw).unwrap();
        let r = e
            .module
            .invoke(input(&e, name, normalized, Some(raw)), &mut host)
            .unwrap();
        fail(&r, "raw_arguments_json: duplicate JSON object key");
        no_effect(&e, &host);
    }
}
#[test]
fn exact_raw_byte_limit_works_and_one_over_refuses_without_effect() {
    let limit = MAX_PROPOSAL + 256;
    let raw = format!("{}{{}}", " ".repeat(limit - 2));
    assert_eq!(raw.len(), limit);
    let e = Env::new();
    let mut host = e.host();
    assert!(
        e.module
            .invoke(input(&e, INIT, json!({}), Some(raw.clone())), &mut host)
            .unwrap()
            .ok
    );
    let over = Env::new();
    let mut host = over.host();
    let r = over
        .module
        .invoke(input(&over, INIT, json!({}), Some(raw + " ")), &mut host)
        .unwrap();
    exact_failure(&r, "correction_memory: raw_arguments_size");
    no_effect(&over, &host);
}
#[test]
fn malformed_or_trailing_raw_is_not_silently_ignored() {
    for (raw, reason) in [
        ("{", "EOF while parsing an object"),
        ("{} {}", "trailing characters"),
    ] {
        let e = Env::new();
        let mut host = e.host();
        let r = e
            .module
            .invoke(input(&e, INIT, json!({}), Some(raw.into())), &mut host)
            .unwrap();
        fail(&r, &format!("raw_arguments_json: {reason}"));
        no_effect(&e, &host);
    }
}
#[test]
fn raw_nesting_guard_precedes_unknown_argument_or_store_errors() {
    let e = Env::new();
    let mut host = e.host();
    let raw = format!("{}0{}", "[".repeat(26), "]".repeat(26));
    let normalized = serde_json::from_str(&raw).unwrap();
    let r = e
        .module
        .invoke(input(&e, INIT, normalized, Some(raw)), &mut host)
        .unwrap();
    fail(&r, "raw_arguments_json: JSON nesting limit exceeded");
    no_effect(&e, &host);
}
#[test]
fn freeform_surface_remains_refused_even_with_matching_raw() {
    let e = Env::new();
    let mut host = e.host();
    let mut call = input(&e, INIT, json!({}), Some("{}".into()));
    call.call.surface = ToolCallSurface::Freeform;
    let r = e.module.invoke(call, &mut host).unwrap();
    exact_failure(&r, "correction_memory: unsupported_call_surface");
    no_effect(&e, &host);
}
