// Scratch-only fixtures around real first-sampling and preparation request builders.
use super::*;
use proteus_contracts::{
    contracts::{
        ContextPreparationOutput, ContextPreparationTarget, WorkflowContinuation,
        WorkflowHistoryUpdate,
    },
    domain::HistoryCompactionReport,
    model_standard::input_estimates::{ModelInputEstimate, ModelPartTokenEstimate},
};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
};

struct Meter;
static ACTIVE: AtomicBool = AtomicBool::new(false);
static REQUESTED: AtomicUsize = AtomicUsize::new(0);
static CALLS: AtomicUsize = AtomicUsize::new(0);
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);

fn record(ptr: *mut u8, size: usize, old: usize) -> *mut u8 {
    if !ptr.is_null() {
        let now = if size >= old {
            LIVE.fetch_add(size - old, Relaxed) + (size - old)
        } else {
            LIVE.fetch_sub(old - size, Relaxed) - (old - size)
        };
        if ACTIVE.load(Relaxed) {
            CALLS.fetch_add(1, Relaxed);
            REQUESTED.fetch_add(size, Relaxed);
            PEAK.fetch_max(now, Relaxed);
        }
    }
    ptr
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        record(unsafe { System.alloc(layout) }, layout.size(), 0)
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        record(unsafe { System.alloc_zeroed(layout) }, layout.size(), 0)
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        record(
            unsafe { System.realloc(ptr, layout, size) },
            size,
            layout.size(),
        )
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        LIVE.fetch_sub(layout.size(), Relaxed);
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static GLOBAL: Meter = Meter;

fn message(number: usize, role: MessageRole, payload: ContentPart) -> CanonicalMessage {
    let fixed = |n| format!("00000000-0000-7000-8000-{n:012x}").parse().unwrap();
    let mut message = CanonicalMessage::new(role, vec![payload]).with_id(fixed(number));
    message.parts[0].part_id = fixed(number + 0x1_0000);
    message
}

fn text(number: usize, role: MessageRole, text: &str) -> CanonicalMessage {
    message(number, role, ContentPart::Text { text: text.into() })
}

#[test]
#[ignore = "differential probe requires fixture environment"]
fn allocation_case() {
    let case = std::env::var("R61_CASE").unwrap();
    let mut input = workflow_input("continue the note");
    input.runtime.conversation = None;
    input.runtime.execution_id =
        serde_json::from_value(json!("00000000-0000-7000-8000-00000000ffff")).unwrap();
    let count = match case.as_str() {
        "first-empty" => 0,
        "first-large" => 96,
        _ => 3,
    };
    input.history = (1..=count)
        .map(|n| {
            let result = ToolResult::ok(
                format!("old-note-{n}"),
                if count < 5 {
                    "previous".into()
                } else {
                    "Прошлый результат 🦀\n".repeat(600)
                },
            )
            .with_metadata(json!({"z":[n,"nested"],"a":{"β":true}}));
            message(n, MessageRole::Tool, ContentPart::ToolResult { result })
        })
        .collect();
    if case != "first-empty" {
        input
            .history
            .push(text(1_000, MessageRole::User, "continue the note"));
    }
    if case.starts_with("first-") && count > 0 {
        let mut compactions = Vec::new();
        if case == "first-restored" {
            input.history[0] = message(
                1,
                MessageRole::Assistant,
                ContentPart::Opaque {
                    format: "fixture.v1".into(),
                    data: json!({"ciphertext":"fixture"}),
                },
            );
            let estimate = ModelInputEstimate {
                parts: vec![ModelPartTokenEstimate {
                    part_id: input.history[0].parts[0].part_id,
                    tokens: 123,
                }],
            };
            let mut report = HistoryCompactionReport::unchanged(
                input.history.len(),
                Some("saved estimate".into()),
            );
            estimate.write_metadata(&mut report.metadata);
            compactions.push(report);
        }
        input.runtime.continuation = Some(WorkflowContinuation {
            attempt: 1,
            reason: "resume".into(),
            current_user_message_id: input.history.last().unwrap().id,
            history: WorkflowHistoryUpdate::new(vec![]).with_compactions(compactions),
        });
    }
    let prepare = case.starts_with("pre-");
    let setup = || {
        let mut host = FakeHost::default();
        if case == "pre-replacement" {
            let mut output = ContextPreparationOutput::changed(
                vec![
                    text(1_001, MessageRole::Assistant, "compact note"),
                    input.history.last().unwrap().clone(),
                ],
                Some("compact note".into()),
            );
            output.trigger_tokens = Some(8100);
            host = host.with_compaction_outputs(vec![output]);
            host.preparation_target = Some(ContextPreparationTarget {
                execution_id: input.runtime.execution_id,
                revision: 7,
            });
        }
        if case == "pre-error" {
            host.compaction_failure =
                Some(ProcessModuleError::new("fixture preparation unavailable"));
        }
        host
    };
    let run = |host: &FakeHost| {
        if prepare {
            crate::host::pre_turn_request(&input, host, &input.history, Some(2000))
        } else {
            crate::host::first_sampling_request(&input, host, &input.history, Some(4200))
        }
    };
    drop(run(&setup()));
    let host = setup();
    let start = LIVE.load(Relaxed);
    PEAK.store(start, Relaxed);
    ACTIVE.store(true, Relaxed);
    let outcome = run(&host);
    ACTIVE.store(false, Relaxed);
    let peak = PEAK.load(Relaxed) - start;
    assert_eq!(host.tool_selections.lock().unwrap().len(), 1);
    assert_eq!(
        host.compactions.lock().unwrap().len(),
        usize::from(prepare && case != "pre-error")
    );
    let wire = match outcome {
        Ok(p) => serde_json::to_string(&(p.request, p.compaction, p.preparation_target)).unwrap(),
        Err(error) => serde_json::to_string(&error.message).unwrap(),
    };
    std::fs::write(std::env::var_os("R61_WIRE").unwrap(), wire).unwrap();
    println!(
        "R61 {} {} {}",
        REQUESTED.load(Relaxed),
        CALLS.load(Relaxed),
        peak
    );
}
