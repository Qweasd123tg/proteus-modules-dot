//! The actual binary through the existing host broker. No builds/install/network
//! are launched by tests; Cargo supplies its already-built executable path.
use std::{path::PathBuf, time::Duration};

use proteus_example_loop_observer::MODULE_ID;
use proteus_module_sdk::{
    contracts::{
        contracts::{
            ExecutionAttribution, HookEvent, HookInput, HookResponse, ModelCallOrigin,
            ProcessComponentExportRef, ProcessHookResponse,
        },
        domain::{ModelRef, ToolCall, ToolResult, new_execution_id},
        model_standard::CanonicalModelRequest,
    },
    protocol::{
        ProcessComponentBinding, ProcessExportBinding,
        v3::{ComponentBroker, ComponentBrokerOptions, InvocationTerminal},
    },
};
use proteus_process_host::ProcessSpec;
use serde_json::json;

#[test]
fn executable_handshake_and_stateful_hook_sequence() {
    let target = ProcessComponentExportRef::new("hook", MODULE_ID);
    let binding = ProcessComponentBinding::new(
        "observer-fixture",
        vec![
            ProcessExportBinding::new(
                "hook",
                MODULE_ID,
                "v6",
                json!({"observed_tools":["read_file"]}),
            )
            .unwrap(),
        ],
    )
    .unwrap();
    let broker = ComponentBroker::connect(
        ProcessSpec::new(env!("CARGO_BIN_EXE_proteus-example-loop-observer")),
        binding,
        ComponentBrokerOptions::default(),
    )
    .unwrap();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .build()
        .unwrap();
    let scope = ExecutionAttribution::detached(new_execution_id());
    let invoke = |event: HookEvent| {
        let input = HookInput {
            event,
            attribution: scope,
            cwd: PathBuf::from("."),
            conversation: None,
        };
        let value = runtime.block_on(async {
            let mut handle = broker
                .start_invocation(
                    &target,
                    "hook.invoke",
                    serde_json::to_value(input).unwrap(),
                    Duration::from_secs(5),
                )
                .await
                .unwrap();
            match handle.result().await.unwrap() {
                InvocationTerminal::Success(value) => value,
                other => panic!("unexpected terminal: {other:?}"),
            }
        });
        serde_json::from_value::<ProcessHookResponse>(value)
            .unwrap()
            .result
    };
    for id in ["one", "two", "three"] {
        assert_eq!(
            invoke(HookEvent::AfterTool {
                call: ToolCall::new(id, "read_file", json!({"path":"a.txt"})),
                result: ToolResult::ok(id.to_owned(), "same")
            }),
            HookResponse::Continue
        );
    }
    let model = || HookEvent::BeforeModel {
        origin: ModelCallOrigin::Direct,
        request: CanonicalModelRequest::new(ModelRef::new("fixture", "fixture"), vec![]),
    };
    let HookResponse::ModelContext {
        instructions,
        messages,
    } = invoke(model())
    else {
        panic!("actual process did not retain observations");
    };
    assert!(messages.is_empty());
    assert!(instructions[0].text.contains("one, two, three"));
    assert_eq!(invoke(model()), HookResponse::Continue);
}
