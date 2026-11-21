use anyhow::{Result, anyhow};
use proteus_contracts::{
    app_protocol::analysis::*,
    contracts,
    domain::{self, *},
    model_standard::{self, *},
    storage::journal::*,
};
use proteus_core::core::{self, SessionStore, canonicalize_session_dir_path};
use proteus_session_semantics::JournalProjection;
use serde_json::json;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    collections::HashMap,
    path::PathBuf,
    sync::atomic::{AtomicUsize, Ordering::Relaxed},
};
mod candidate;
mod stock;
#[path = "support.rs"]
mod test_support;
struct Meter;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn add(n: usize) {
    CALLS.fetch_add(1, Relaxed);
    BYTES.fetch_add(n, Relaxed);
}
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        add(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        add(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        add(n);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static METER: Meter = Meter;
fn meas<F, T>(f: F) -> (T, (usize, usize))
where
    F: FnOnce() -> T,
{
    let before = (CALLS.load(Relaxed), BYTES.load(Relaxed));
    let r = std::hint::black_box(f());
    (
        r,
        (
            CALLS.load(Relaxed) - before.0,
            BYTES.load(Relaxed) - before.1,
        ),
    )
}
fn projection(records: Vec<JournalRecord>) -> JournalProjection {
    JournalProjection {
        records,
        history: vec![],
        history_revision: 0,
        interrupted_turns: vec![],
        interrupted_model_exchanges: vec![],
        interrupted_context_builds: vec![],
        unresolved_tool_calls: vec![],
        unsettled_turns: vec![],
    }
}
fn msg(t: &str) -> CanonicalMessage {
    CanonicalMessage::text(MessageRole::Assistant, t)
}
fn task(t: &str) -> AgentTask {
    AgentTask::new(t, "/synthetic".into())
}
fn record_set(s: SessionId, t: TurnId, text: &str, k: usize) -> Vec<JournalRecord> {
    use contracts::*;
    let th = new_thread_id();
    let x = new_execution_id();
    let id = new_exchange_id();
    let owner = OperationOwner::Workflow;
    let ctx = new_record_id();
    let output = ContextPreparationOutput::unchanged(vec![msg("diag")]);
    let diagnostics = output.diagnostics();
    let event = HookEvent::BeforeContext {
        input: ContextPreparationInput::new(
            if k == 7 {
                vec![msg("invalid unchanged source")]
            } else {
                output.messages.clone()
            },
            None,
        ),
        model_capabilities: None,
        output,
        target: None,
    };
    let trace = HookTrace {
        owner: owner.clone(),
        input: HookInput {
            event,
            attribution: ExecutionAttribution::for_turn(x, s, th, t),
            cwd: ".".into(),
            conversation: None,
        },
        steps: vec![HookStep {
            invocation_id: new_record_id(),
            module_id: "diagnostics".into(),
            outcome: HookStepOutcome::Accepted {
                response: HookResponse::ContextPreparationDiagnostics { diagnostics },
            },
        }],
        output: None,
    };
    let call = ToolCall::new("one", "tool", json!({"nested":["source",2]}));
    let request = CanonicalModelRequest::new(ModelRef::new("fixture", "old"), vec![msg(text)]);
    let mut entries = vec![
        JournalEntry::TurnOpened(TurnOpened {
            task: task("Юникод 🙂"),
            intent: None,
            base_history_revision: 0,
            module_epoch: 7,
            config_snapshot: json!({"a":[1,"x"]}),
        }),
        JournalEntry::ContextRequestRecorded(ContextRequestRecorded {
            invocation_id: ctx,
            task: task("ctx"),
        }),
        JournalEntry::ContextResponseRecorded(ContextResponseRecorded {
            invocation_id: ctx,
            outcome: ContextBuildOutcome::Error {
                message: "no".into(),
                causes: vec![],
            },
        }),
        JournalEntry::HookInvoked(trace),
        JournalEntry::ModelRequestRecorded(ModelRequestRecorded {
            exchange_id: id,
            origin: ModelCallOrigin::Auxiliary,
            owner: owner.clone(),
            request,
        }),
        JournalEntry::ModelMessageRecorded(ModelMessageRecorded {
            exchange_id: id,
            message: msg("partial"),
        }),
        JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
            exchange_id: id,
            outcome: if k % 2 == 0 {
                ModelResponseOutcome::Response {
                    response: CanonicalModelResponse::new(msg("OK"), vec![], FinishReason::Stop),
                }
            } else {
                ModelResponseOutcome::Error {
                    failure: ModelFailure::other("fail"),
                }
            },
        }),
        JournalEntry::ToolCallRecorded(ToolCallRecorded {
            call: call.clone(),
            phase: ToolCallRecordPhase::Requested { owner },
        }),
        JournalEntry::ToolCallRecorded(ToolCallRecorded {
            call: call.clone(),
            phase: ToolCallRecordPhase::ApprovalRequested {
                reason: "why".into(),
            },
        }),
        JournalEntry::ToolCallRecorded(ToolCallRecorded {
            call,
            phase: ToolCallRecordPhase::Resolved {
                resolution: ToolCallResolution::Approved,
            },
        }),
        JournalEntry::ToolEffectRecorded(ToolResultRecorded {
            result: ToolResult::ok("one".into(), "effect"),
        }),
        JournalEntry::ToolResultRecorded(ToolResultRecorded {
            result: ToolResult::ok("one".into(), "final"),
        }),
        JournalEntry::HistoryMutated(HistoryMutated {
            previous_revision: 0,
            new_revision: 1,
            mutation: HistoryMutationKind::Append,
            messages: vec![msg("journal")],
            compaction: Some(HistoryCompactionReport::unchanged(1, None)),
            tool_results: vec![],
        }),
        JournalEntry::SubagentSessionBoundRecorded(SubagentSessionBinding {
            source_call_id: "one".into(),
            child_thread_id: new_thread_id(),
            session_id: new_session_id(),
            session_dir: ".".into(),
        }),
        JournalEntry::TurnSettled(TurnSettled {
            status: [
                TurnSettlementStatus::Success,
                TurnSettlementStatus::Error,
                TurnSettlementStatus::Canceled,
                TurnSettlementStatus::Timeout,
            ][k % 4],
            output: Some(AgentOutput::text("answer")),
            error: None,
        }),
    ];
    entries
        .drain(..)
        .enumerate()
        .map(|(i, entry)| JournalRecord {
            schema_version: JOURNAL_SCHEMA_VERSION,
            record_id: new_record_id(),
            session_seq: i as u64 + 1,
            timestamp_ms: i as i64,
            session_id: s,
            execution_id: Some(x),
            thread_id: Some(th),
            turn_id: Some(t),
            entry,
        })
        .collect()
}
fn wire(r: Result<AppSessionAnalysis>) -> Result<Vec<u8>, String> {
    r.map(|x| serde_json::to_vec(&x).unwrap())
        .map_err(|e| format!("{e:#}"))
}
#[test]
fn parity() {
    let (s, t, u, missing) = (
        new_session_id(),
        new_turn_id(),
        new_turn_id(),
        new_turn_id(),
    );
    let (mut ok, mut errors) = (0, 0);
    for shape in 0..8 {
        let a = record_set(s, t, "first", shape);
        let b = record_set(s, u, "second", shape + 1);
        let mut rows = Vec::new();
        for (i, (j, k)) in a.into_iter().zip(b).enumerate() {
            rows.push(j);
            if i % 2 == 0 || shape % 2 == 0 {
                rows.push(k)
            }
        }
        if shape & 2 != 0 {
            rows.reverse()
        }
        if shape & 4 != 0 {
            for (i, r) in rows.iter_mut().enumerate() {
                if i % 3 == 0 {
                    r.turn_id = None
                }
            }
        }
        for n in 0..=rows.len() {
            for selection in [None, Some(t), Some(u), Some(missing)] {
                let p = projection(rows[..n].to_vec());
                let before = wire(stock::run(s, p.clone(), selection));
                let after = wire(candidate::run(s, p, selection));
                assert_eq!(before, after);
                if before.is_ok() { ok += 1 } else { errors += 1 }
            }
        }
    }
    println!("Complete DTO/error parity: {ok} successful reports plus {errors} exact errors");
}
#[test]
fn allocations() {
    let (s, t, other) = (new_session_id(), new_turn_id(), new_turn_id());
    for (label, bytes, target) in [
        ("empty", 0, 0),
        ("small selected", 16, 1),
        ("large selected", 1 << 20, 1),
        ("large NOT selected", 1 << 20, 2),
    ] {
        let mut rows = vec![];
        if target != 0 {
            rows = record_set(s, t, &"a".repeat(bytes), 0);
            rows.extend(record_set(s, other, "small", 1));
        }
        let r = match target {
            0 => None,
            1 => Some(t),
            _ => Some(other),
        };
        let mut counts = [(0, 0); 2];
        let mut expected = None;
        for (step, arm) in [0, 1, 1, 0].into_iter().enumerate() {
            let p = projection(rows.clone());
            let (result, count) = meas(|| {
                if arm == 0 {
                    stock::run(s, p, r)
                } else {
                    candidate::run(s, p, r)
                }
            });
            let body = wire(result).unwrap();
            if let Some(prev) = &expected {
                assert_eq!(&body, prev)
            } else {
                expected = Some(body)
            };
            if step >= 2 {
                assert_eq!(counts[arm], count)
            } else {
                counts[arm] = count
            }
        }
        println!(
            "{label}: calls {} -> {}, requested bytes {} -> {}",
            counts[0].0, counts[1].0, counts[0].1, counts[1].1
        );
        if target == 1 && bytes >= 1 << 20 {
            assert!(counts[0].1 - counts[1].1 >= 1 << 20)
        }
    }
}

// Isolated guard, no I/O: both arms drop input during projection; the response
// drops outside the timed interval. This is not HTTP latency.
#[cfg(target_os = "linux")]
#[test]
fn scan_control() {
    use std::ffi::{c_int, c_long};
    #[repr(C)]
    struct Timespec {
        seconds: c_long,
        nanos: c_long,
    }
    unsafe extern "C" {
        fn clock_gettime(clock: c_int, t: *mut Timespec) -> c_int;
    }
    fn ns() -> u64 {
        let mut t = Timespec {
            seconds: 0,
            nanos: 0,
        };
        assert_eq!(unsafe { clock_gettime(3, &mut t) }, 0); // Linux CLOCK_THREAD_CPUTIME_ID
        t.seconds as u64 * 1_000_000_000 + t.nanos as u64
    }
    let (s, t, other) = (new_session_id(), new_turn_id(), new_turn_id());
    for (label, position) in [("first", 0), ("last", 128), ("all", 129)] {
        let small = record_set(s, t, "small", 0);
        let other = record_set(s, other, "small", 1);
        let mut all = Vec::new();
        for i in 0..129 {
            all.extend(
                if i == position || position == 129 {
                    &small
                } else {
                    &other
                }
                .iter()
                .cloned(),
            );
        }
        let mut samples = [Vec::new(), Vec::new()];
        for (i, arm) in [0, 1, 1, 0].into_iter().cycle().take(52).enumerate() {
            let input = projection(all.clone());
            let start = ns();
            let output = std::hint::black_box(if arm == 0 {
                stock::run(s, input, Some(t))
            } else {
                candidate::run(s, input, Some(t))
            })
            .unwrap();
            let elapsed = ns() - start;
            if i >= 4 {
                samples[arm].push(elapsed);
            }
            std::hint::black_box(output);
        }
        for s in &mut samples {
            s.sort_unstable();
        }
        println!(
            "1935 mixed records, selected group {label}: median thread CPU {} -> {} ns (24/arm), synthetic no I/O",
            samples[0][12], samples[1][12]
        );
    }
}
