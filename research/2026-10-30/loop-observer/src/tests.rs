use std::{
    cell::Cell,
    path::PathBuf,
    time::{Duration, Instant},
};

use proteus_module_sdk::contracts::{
    contracts::{ExecutionAttribution, HookTurnStatus, apply_hook_response},
    domain::{
        ModelRef, ToolCall, ToolResult, new_execution_id, new_session_id, new_thread_id,
        new_turn_id,
    },
    model_standard::CanonicalModelRequest,
};
use serde_json::json;

use super::*;

fn binding(config: Value) -> ProcessComponentExportInitialize {
    ProcessComponentExportInitialize::new(
        "hook",
        MODULE_ID,
        "v6",
        ProcessModuleComposition::OrderedMany,
        config,
        Vec::<String>::new(),
    )
}

fn observer(extra: Value) -> LoopObserver {
    let mut config = json!({"observed_tools": ["read_file", "rg_search"]});
    config
        .as_object_mut()
        .unwrap()
        .extend(extra.as_object().unwrap().clone());
    LoopObserver::new(binding(config)).unwrap()
}

fn input(attribution: ExecutionAttribution, event: HookEvent) -> HookInput {
    HookInput {
        attribution,
        event,
        cwd: PathBuf::from("."),
        conversation: None,
    }
}

fn returned(id: &str, name: &str, output: &str) -> HookEvent {
    HookEvent::AfterTool {
        call: ToolCall::new(id, name, json!({"path":"a.txt"})),
        result: ToolResult::ok(id.to_owned(), output),
    }
}

fn model(origin: ModelCallOrigin) -> HookEvent {
    HookEvent::BeforeModel {
        origin,
        request: CanonicalModelRequest::new(ModelRef::new("fixture", "fixture"), vec![])
            .with_instructions(vec![InstructionBlock::new(
                InstructionKind::Project,
                "keep existing",
                50,
            )]),
    }
}

fn apply(
    observer: &LoopObserver,
    attribution: ExecutionAttribution,
    event: HookEvent,
) -> HookResponse {
    let original = event.clone();
    let response = observer
        .evaluate(input(attribution, event), || false)
        .unwrap();
    apply_hook_response(&original, &response).expect("response must obey actual hook contract");
    response
}

fn prime(observer: &LoopObserver, attribution: ExecutionAttribution) {
    for id in ["a", "b", "c"] {
        assert_eq!(
            apply(observer, attribution, returned(id, "read_file", "same")),
            HookResponse::Continue
        );
    }
}

#[test]
fn threshold_emits_one_advisory_and_preserves_existing_context() {
    let observer = observer(json!({}));
    let scope = ExecutionAttribution::detached(new_execution_id());
    prime(&observer, scope);
    let HookResponse::ModelContext {
        messages,
        instructions,
    } = apply(&observer, scope, model(ModelCallOrigin::Direct))
    else {
        panic!("expected advisory");
    };
    assert!(messages.is_empty());
    assert_eq!(instructions[0].text, "keep existing");
    assert_eq!(instructions.len(), 2);
    assert!(instructions[1].text.contains("a, b, c"));
    assert!(instructions[1].text.contains("intentional polling"));
    assert_eq!(
        apply(&observer, scope, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
}

#[test]
fn duplicate_delivery_does_not_count_and_new_evidence_can_report_again() {
    let observer = observer(json!({}));
    let scope = ExecutionAttribution::detached(new_execution_id());
    for _ in 0..5 {
        apply(&observer, scope, returned("a", "read_file", "same"));
    }
    assert_eq!(
        apply(&observer, scope, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
    for id in ["b", "c"] {
        apply(&observer, scope, returned(id, "read_file", "same"));
    }
    assert!(matches!(
        apply(&observer, scope, model(ModelCallOrigin::Direct)),
        HookResponse::ModelContext { .. }
    ));
    prime(&observer, scope); // same IDs stay deduplicated after the notice
    assert_eq!(
        apply(&observer, scope, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
    for id in ["d", "e", "f"] {
        apply(&observer, scope, returned(id, "read_file", "same"));
    }
    assert!(matches!(
        apply(&observer, scope, model(ModelCallOrigin::Direct)),
        HookResponse::ModelContext { .. }
    ));
}

#[test]
fn progress_unobserved_tool_and_oversize_clear_pending_notice() {
    for event in [
        returned("d", "read_file", "changed"),
        returned("a", "read_file", "conflicting redelivery"),
        returned("d", "wait_for_ci", "pending"),
        returned("d", "read_file", &"x".repeat(40000)),
    ] {
        let observer = observer(json!({}));
        let scope = ExecutionAttribution::detached(new_execution_id());
        prime(&observer, scope);
        apply(&observer, scope, event);
        assert_eq!(
            apply(&observer, scope, model(ModelCallOrigin::Direct)),
            HookResponse::Continue
        );
    }
}

#[test]
fn auxiliary_model_does_not_consume_notice_and_before_tool_is_never_blocked() {
    let observer = observer(json!({}));
    let scope = ExecutionAttribution::detached(new_execution_id());
    prime(&observer, scope);
    assert_eq!(
        apply(&observer, scope, model(ModelCallOrigin::Auxiliary)),
        HookResponse::Continue
    );
    let call = ToolCall::new("d", "read_file", json!({"path":"a.txt"}));
    assert_eq!(
        apply(
            &observer,
            scope,
            HookEvent::BeforeTool {
                call,
                spec: None,
                blocked: Some("preexisting deny".into())
            }
        ),
        HookResponse::Continue
    );
    assert!(matches!(
        apply(&observer, scope, model(ModelCallOrigin::Direct)),
        HookResponse::ModelContext { .. }
    ));
}

#[test]
fn execution_and_agent_turn_are_both_part_of_scope() {
    let observer = observer(json!({}));
    let id = new_execution_id();
    let session = new_session_id();
    let thread = new_thread_id();
    let a = ExecutionAttribution::for_turn(id, session, thread, new_turn_id());
    let b = ExecutionAttribution::for_turn(id, session, thread, new_turn_id());
    prime(&observer, a);
    for scope in [
        b,
        ExecutionAttribution::detached(id),
        ExecutionAttribution::detached(new_execution_id()),
    ] {
        assert_eq!(
            apply(&observer, scope, model(ModelCallOrigin::Direct)),
            HookResponse::Continue
        );
    }
    assert!(matches!(
        apply(&observer, a, model(ModelCallOrigin::Direct)),
        HookResponse::ModelContext { .. }
    ));
}

#[test]
fn settled_turn_and_new_process_forget_observations() {
    let scope = ExecutionAttribution::detached(new_execution_id());
    let first = observer(json!({}));
    prime(&first, scope);
    apply(
        &first,
        scope,
        HookEvent::TurnSettled {
            status: HookTurnStatus::Canceled,
            output: None,
            error: None,
        },
    );
    assert_eq!(
        apply(&first, scope, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
    prime(&first, scope);
    assert_eq!(
        apply(&observer(json!({})), scope, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
}

#[test]
fn idle_expiry_and_scope_eviction_discard_evidence() {
    let observer = observer(json!({"max_scopes":1,"idle_ttl_seconds":1}));
    let a = ExecutionAttribution::detached(new_execution_id());
    let b = ExecutionAttribution::detached(new_execution_id());
    let now = Instant::now();
    for id in ["a", "b", "c"] {
        observer
            .evaluate_at(input(a, returned(id, "read_file", "same")), || false, now)
            .unwrap();
    }
    assert_eq!(
        observer
            .evaluate_at(
                input(a, model(ModelCallOrigin::Direct)),
                || false,
                now + Duration::from_secs(1)
            )
            .unwrap(),
        HookResponse::Continue
    );
    prime(&observer, a);
    apply(&observer, b, returned("d", "read_file", "same"));
    assert_eq!(
        apply(&observer, a, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
}

#[test]
fn call_id_mismatch_is_a_gap_not_evidence() {
    let observer = observer(json!({}));
    let scope = ExecutionAttribution::detached(new_execution_id());
    prime(&observer, scope);
    apply(
        &observer,
        scope,
        HookEvent::AfterTool {
            call: ToolCall::new("d", "read_file", json!({})),
            result: ToolResult::ok("other".into(), "same"),
        },
    );
    assert_eq!(
        apply(&observer, scope, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
}

#[test]
fn long_ids_clear_pending_and_notice_labels_remain_bounded() {
    let module = observer(json!({"threshold":16}));
    let scope = ExecutionAttribution::detached(new_execution_id());
    for index in 0..16 {
        let id = format!("{index:02}{}", "x".repeat(126));
        apply(&module, scope, returned(&id, "read_file", "same"));
    }
    let HookResponse::ModelContext { instructions, .. } =
        apply(&module, scope, model(ModelCallOrigin::Direct))
    else {
        panic!("expected bounded notice");
    };
    assert!(instructions.last().unwrap().text.len() < 4096);
    let module = observer(json!({}));
    prime(&module, scope);
    apply(
        &module,
        scope,
        returned(&"x".repeat(129), "read_file", "same"),
    );
    assert_eq!(
        apply(&module, scope, model(ModelCallOrigin::Direct)),
        HookResponse::Continue
    );
}

#[test]
fn signatures_preserve_result_metadata_error_and_surface() {
    let call = ToolCall::new("a", "read_file", json!({"a":1,"b":2}));
    let result = ToolResult::ok("a".into(), "same");
    let signature = signature::build(&call, &result, 32768, &|| false)
        .unwrap()
        .unwrap();
    let mut changed = result.clone();
    changed.metadata = json!({"changed":true});
    assert_ne!(
        signature::build(&call, &changed, 32768, &|| false)
            .unwrap()
            .unwrap(),
        signature
    );
    changed = result.clone();
    changed.error = Some("different".into());
    assert_ne!(
        signature::build(&call, &changed, 32768, &|| false)
            .unwrap()
            .unwrap(),
        signature
    );
    let mut changed_call = call.clone();
    changed_call.id = "b".into();
    let mut changed_result = result;
    changed_result.call_id = "b".into();
    assert_eq!(
        signature::build(&changed_call, &changed_result, 32768, &|| false)
            .unwrap()
            .unwrap(),
        signature
    );
    changed_call.surface = proteus_module_sdk::contracts::domain::ToolCallSurface::Freeform;
    assert_ne!(
        signature::build(&changed_call, &changed_result, 32768, &|| false)
            .unwrap()
            .unwrap(),
        signature
    );
}

#[test]
fn canonical_args_and_exact_size_boundary() {
    let call = ToolCall::new(
        "a",
        "read_file",
        serde_json::from_str(r#"{"b":[2,1],"a":{"z":0,"a":true}}"#).unwrap(),
    );
    let mut reordered = call.clone();
    reordered.args = serde_json::from_str(r#"{"a":{"a":true,"z":0},"b":[2,1]}"#).unwrap();
    let result = ToolResult::ok("a".into(), "é\"\\");
    let bytes = signature::build(&call, &result, 32768, &|| false)
        .unwrap()
        .unwrap();
    assert_eq!(
        signature::build(&reordered, &result, bytes.len(), &|| false)
            .unwrap()
            .unwrap(),
        bytes
    );
    assert!(
        signature::build(&call, &result, bytes.len() - 1, &|| false)
            .unwrap()
            .is_none()
    );
}

#[test]
fn complex_args_skip_without_inventing_partial_signature() {
    let mut deep = json!(0);
    for _ in 0..34 {
        deep = json!([deep]);
    }
    for args in [deep, json!(vec![0; 4097])] {
        assert!(
            signature::build(
                &ToolCall::new("a", "read_file", args),
                &ToolResult::ok("a".into(), "same"),
                32768,
                &|| false
            )
            .unwrap()
            .is_none()
        );
    }
}

#[test]
fn cancellation_during_writer_terminates_instead_of_retrying_interrupted() {
    let calls = Cell::new(0);
    let canceled = || {
        calls.set(calls.get() + 1);
        calls.get() > 3
    };
    assert!(
        signature::build(
            &ToolCall::new("a", "read_file", json!({"a":[1,2,3]})),
            &ToolResult::ok("a".into(), "same"),
            32768,
            &canceled
        )
        .is_err()
    );
    assert!(calls.get() < 20);
    assert!(
        observer(json!({}))
            .evaluate(
                input(
                    ExecutionAttribution::detached(new_execution_id()),
                    model(ModelCallOrigin::Direct)
                ),
                || true
            )
            .is_err()
    );
}

#[test]
fn factory_and_presentation_schema_are_explicit() {
    let module = observer(json!({}));
    module.manifest().config_schema.unwrap().validate().unwrap();
    for config in [
        json!({}),
        json!({"observed_tools":[]}),
        json!({"observed_tools":["read_file"],"unknown":true}),
        json!({"observed_tools":["read_file"],"max_scopes":128,"max_observation_bytes":262144}),
    ] {
        assert!(LoopObserver::new(binding(config)).is_err());
    }
    let mut wrong = binding(json!({"observed_tools":["read_file"]}));
    wrong.composition = ProcessModuleComposition::SelectOne;
    assert!(LoopObserver::new(wrong).is_err());
    let mut wrong = binding(json!({"observed_tools":["read_file"]}));
    wrong.module_id = "not-the-observer".into();
    assert!(LoopObserver::new(wrong).is_err());
    let mut wrong = binding(json!({"observed_tools":["read_file"]}));
    wrong.contract_version = "v5".into();
    assert!(LoopObserver::new(wrong).is_err());
}

#[test]
fn concurrent_distinct_scopes_do_not_share_observations() {
    let observer = std::sync::Arc::new(observer(json!({})));
    let threads = (0..8)
        .map(|_| {
            let observer = observer.clone();
            std::thread::spawn(move || {
                let scope = ExecutionAttribution::detached(new_execution_id());
                prime(&observer, scope);
                assert!(matches!(
                    apply(&observer, scope, model(ModelCallOrigin::Direct)),
                    HookResponse::ModelContext { .. }
                ));
            })
        })
        .collect::<Vec<_>>();
    for thread in threads {
        thread.join().unwrap();
    }
}
