#![allow(dead_code, unused_imports)]

mod agents {
    pub mod codex;
}
use agents::codex::{Event, ValueProjection, parity_clip, parity_history, projection, stock};
use serde_json::{Value, json};
use std::hint::black_box;

mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static A: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(new, Relaxed);
            unsafe { System.realloc(p, layout, new) }
        }
    }
    pub fn read() -> (usize, usize) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}

const CAP: usize = 128 * 1024;

fn data(kind: &str) -> Value {
    json!({
        "id": "item:opaque:suffix",
        "type": kind,
        "text": "Visible результат",
        "summary": ["visible", {"text":"second"}],
        "content": ["paragraph", {"text":"more"}],
        "command": "synthetic",
        "cwd": "/synthetic",
        "processId": 16,
        "server": "local",
        "tool": "fixture",
        "result": {"text":"fixture"},
        "changes": [{"path":"/synthetic/example"}],
        "arguments": {"arg":"value"},
        "receiverThreadIds": ["child:opaque"],
        "agentsStates": {"child:opaque":{"status":"running"}},
        "query": "synthetic",
        "name": "sample",
        "output": ["one", "two"],
    })
}

fn matrix() {
    let kinds = [
        "agentMessage",
        "userMessage",
        "reasoning",
        "plan",
        "commandExecution",
        "fileChange",
        "mcpToolCall",
        "dynamicToolCall",
        "collabAgentToolCall",
        "webSearch",
        "functionCallOutput",
        "unknownNewType",
    ];
    let events = [
        "item/started",
        "item/completed",
        "item/agentMessage/delta",
        "item/plan/delta",
        "item/reasoning/summaryTextDelta",
        "item/reasoning/summaryPartAdded",
        "item/commandExecution/outputDelta",
        "item/fileChange/outputDelta",
        "turn/started",
        "turn/completed",
        "serverRequest/resolved",
        "turn/plan/updated",
        "thread/tokenUsage/updated",
        "error",
        "unknownNewNotice",
    ];
    let turn_ids = [
        None,
        Some(json!(null)),
        Some(json!(17)),
        Some(json!(true)),
        Some(json!(["opaque:1"])),
        Some(json!({"id":"turn"})),
        Some(json!("")),
        Some(json!("turn:opaque:one")),
        Some(json!(" turn:я 🦀\n ")),
    ];
    let mut n = 0;
    let mut hist = 0;
    for kind in kinds {
        for status in [Value::Null, json!("failed"), json!(""), json!(9)] {
            for turn in &turn_ids {
                for time in [Value::Null, json!(-5), json!(9000), json!("bad")] {
                    let mut item = data(kind);
                    item["status"] = status.clone();
                    let mut params = json!({
                        "item":item, "itemId":"item:delta", "delta":" δ 🦀",
                        "turn":{"id":"done:opaque","status":"interrupted","error":{"message":"text"}},
                        "requestId": "permission:opaque",
                        "startedAtMs": time,
                        "completedAtMs": time
                    });
                    if let Some(turn) = turn {
                        params["turnId"] = turn.clone();
                    }
                    for method in events {
                        assert_eq!(
                            stock::notification(method, &params),
                            projection::notification(method, &params)
                        );
                        n += 1;
                    }
                    parity_history(&params);
                    hist += 1;
                }
            }
        }
    }
    let mut limits = 0;
    for excess in [0, 1, 2, 64] {
        for ch in ['a', 'é', 'я', '🦀'] {
            for left in [1, 2, 3, 4] {
                let text = format!("{}{}{}", "x".repeat(CAP - left), ch, "a".repeat(excess));
                parity_clip(&text);
                let mut p = json!({"turnId":text, "item":data("agentMessage")});
                for method in ["item/started", "item/completed"] {
                    let (Some(Event::ItemUpsert(old)), Some(Event::ItemUpsert(new))) = (
                        stock::notification(method, &p),
                        projection::notification(method, &p),
                    ) else {
                        panic!("expected items")
                    };
                    assert!(old == new);
                    assert!(new.turn_id.capacity() <= old.turn_id.capacity());
                    n += 1;
                }
                parity_history(&p);
                hist += 1;
                p["item"]["id"] = Value::Null;
                assert_eq!(
                    stock::notification("item/completed", &p),
                    projection::notification("item/completed", &p)
                );
                n += 1;
                limits += 1;
            }
        }
    }
    assert_eq!(n, 26112);
    assert_eq!(hist, 1792);
    assert_eq!(limits, 64);
    println!(
        "PASS {n} live notification values, {hist} borrowed history values, {limits} UTF-8 boundary/capacity probes"
    );
}

fn measure<F, T>(arm: &str, name: &str, f: F)
where
    F: FnOnce() -> T,
{
    let before = counter::read();
    let result = black_box(f());
    let after = counter::read();
    black_box(&result);
    println!(
        "alloc\t{arm}\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations(arm: &str) {
    let project: ValueProjection = match arm {
        "stock" => stock::notification,
        "candidate" => projection::notification,
        _ => panic!("arm"),
    };
    let params = json!({"turnId":"turn:just-an-opaque-identifier", "item":data("agentMessage"), "startedAtMs":24});
    let command = json!({"turnId":"turn:just-an-opaque-identifier", "item":data("commandExecution"), "completedAtMs":32});
    let long =
        json!({"turnId":format!("{}🦀 remainder", "x".repeat(CAP-2)), "item":data("agentMessage")});
    let delta = json!({"turnId":params["turnId"],"itemId":"opaque:row","delta":"just text"});
    let empty = json!({"item":data("agentMessage")});
    let invalid = json!({"turnId":params["turnId"],"item":{"type":"agentMessage"}});
    for (name, method, params) in [
        ("assistant-start", "item/started", &params),
        ("command-completion", "item/completed", &command),
        ("long-turn-id", "item/completed", &long),
        ("empty-turn-id", "item/started", &empty),
        ("ordinary-delta", "item/agentMessage/delta", &delta),
        ("invalid-item", "item/completed", &invalid),
    ] {
        measure(arm, name, || project(black_box(method), black_box(params)));
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        matrix();
    } else {
        allocations(&arm);
    }
}
