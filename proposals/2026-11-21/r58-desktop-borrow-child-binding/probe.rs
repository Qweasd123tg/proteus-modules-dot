#![allow(dead_code, unused_imports)]

mod agents {
    pub mod codex;
}
mod stock;
mod transcript;

use proteus_contracts::app_protocol::{
    AppSubagentSession, AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool,
};
use serde_json::{Value, json};
use std::hint::black_box;
use transcript::{Entry, Transcript, subagent};

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

fn session(id: u128, path: &str) -> AppSubagentSession {
    AppSubagentSession {
        session_id: uuid::Uuid::from_u128(id),
        session_dir: path.into(),
    }
}

fn tool(kind: Value, child: Value, binding: Option<Value>, sequence: usize) -> AppTranscriptTool {
    let mut metadata = json!({"tool": kind, "child_thread_id": child});
    if let Some(binding) = binding {
        metadata["subagent_session"] = binding;
    }
    AppTranscriptTool {
        terminal: None,
        call_id: format!("synthetic-call-{sequence}"),
        name: "arbitrary-user-visible-name".into(),
        args: json!({"agent_type":"explorer"}),
        effective_args: None,
        status: "done".into(),
        result: None,
        metadata,
    }
}

fn progress(child: &str, binding: Option<AppSubagentSession>) -> AppTranscriptSubagent {
    AppTranscriptSubagent {
        child_thread_id: child.into(),
        session: binding,
        role: "explorer".into(),
        description: None,
        status: "running".into(),
        iterations: None,
        tools: Vec::new(),
    }
}

fn message(
    tool: Option<AppTranscriptTool>,
    subagent: Option<AppTranscriptSubagent>,
    i: usize,
) -> AppTranscriptMessage {
    AppTranscriptMessage {
        timestamp_ms: Some(i as i64),
        message_id: Some(uuid::Uuid::from_u128(i as u128 + 1)),
        phase: None,
        role: if tool.is_none() && subagent.is_none() {
            "assistant"
        } else {
            "system"
        }
        .into(),
        text: "synthetic transcript row".into(),
        images: vec![],
        tool,
        subagent,
        streaming: false,
    }
}

fn parity() {
    let canonical = session(42, "/synthetic/child/⌘");
    let path_conflict = session(42, "/synthetic/other-path");
    let id_conflict = session(43, "/synthetic/child/⌘");
    let relative = session(42, "relative/child");
    let id = canonical.session_id.to_string();
    let valid_obj = json!(&canonical);
    let mut swapped_obj = json!({"session_dir": &canonical.session_dir});
    swapped_obj["session_id"] = json!(&id);
    let binding = [
        None,
        Some(Value::Null),
        Some(valid_obj.clone()),
        Some(swapped_obj),
        Some(json!([&id, &canonical.session_dir])),
        Some(json!([&id, &canonical.session_dir, true])),
        Some(json!([&id])),
        Some(json!(&path_conflict)),
        Some(json!(&id_conflict)),
        Some(json!(&relative)),
        Some(json!({"session_id": "not-a-uuid", "session_dir": &canonical.session_dir})),
        Some(json!({"session_id": 42, "session_dir": &canonical.session_dir})),
        Some(json!({"session_id": null, "session_dir": &canonical.session_dir})),
        Some(json!({"session_id": &id, "session_dir": ["/synthetic/child"]})),
        Some(json!({"session_id": &id, "session_dir": null})),
        Some(json!({"session_id": &id, "session_dir": ""})),
        Some(json!({"session_id": &id})),
        Some(json!({"session_dir": &canonical.session_dir})),
        Some(
            json!({"session_id": &id, "session_dir": &canonical.session_dir, "extra": {"nested": [1, 2, 3]}}),
        ),
        Some(json!({"unknown": &valid_obj})),
        Some(json!({})),
        Some(json!([])),
        Some(json!("not an object")),
        Some(json!(1)),
        Some(json!(true)),
    ];
    let live = [
        None,
        Some(progress("child", None)),
        Some(progress("child", Some(canonical.clone()))),
        Some(progress("child", Some(path_conflict))),
        Some(progress("child", Some(id_conflict))),
        Some(progress("other", Some(canonical.clone()))),
        Some(progress("child", Some(relative))),
    ];
    let mut pages = Vec::new();
    for first in &live {
        for second in &live {
            let mut page = Transcript::default();
            page.reset(vec![
                message(None, first.clone(), 0),
                message(None, None, 1),
                message(None, second.clone(), 2),
            ]);
            pages.push(page);
        }
    }
    let mut parse = 0;
    let mut dedup = 0;
    for kind in [
        json!("task"),
        json!("spawn_agent"),
        json!("followup_task"),
        json!("read_file"),
        json!(""),
        json!(null),
        json!({}),
    ] {
        for child in [
            json!("child"),
            json!("other"),
            json!(""),
            json!(null),
            json!(42),
            json!(["child"]),
        ] {
            for metadata in &binding {
                let tool = tool(kind.clone(), child.clone(), metadata.clone(), 0);
                assert_eq!(
                    stock::task_session(&tool),
                    subagent::task_session(&tool),
                    "metadata {:?}",
                    tool.metadata
                );
                parse += 1;
                for page in &pages {
                    assert_eq!(
                        stock::progress_row(page.entries(), &tool),
                        subagent::progress_row(page.entries(), &tool),
                        "metadata {:?}",
                        tool.metadata
                    );
                    dedup += 1;
                }
            }
        }
    }
    for metadata in [Value::Null, json!(17), json!("task"), json!([valid_obj])] {
        let mut tool = tool(json!("task"), json!("child"), None, 0);
        tool.metadata = metadata;
        assert_eq!(subagent::task_session(&tool), None);
        assert_eq!(stock::task_session(&tool), subagent::task_session(&tool));
        parse += 1;
        for page in &pages {
            assert_eq!(
                stock::progress_row(page.entries(), &tool),
                subagent::progress_row(page.entries(), &tool)
            );
            dedup += 1;
        }
    }
    println!("PASS {parse} typed decode and {dedup} exact progress-row comparisons");
}

fn measure<T>(arm: &str, name: &str, call: impl FnOnce() -> T) {
    let before = counter::read();
    let result = black_box(call());
    let after = counter::read();
    black_box(&result);
    println!(
        "alloc\t{arm}\t{name}\t{}\t{}",
        after.0 - before.0,
        after.1 - before.1
    );
}

fn allocations(arm: &str) {
    type Decode = fn(&AppTranscriptTool) -> Option<AppSubagentSession>;
    type Progress = fn(&[Entry], &AppTranscriptTool) -> Option<usize>;
    let (decode, find): (Decode, Progress) = match arm {
        "stock" => (stock::task_session, stock::progress_row),
        "candidate" => (subagent::task_session, subagent::progress_row),
        _ => panic!("expected stock or candidate"),
    };
    let binding = session(42, "/synthetic/workspaces/forest/subagent/session");
    let mut page = Transcript::default();
    page.reset(vec![
        message(
            Some(tool(
                json!("task"),
                json!("child"),
                Some(json!(&binding)),
                0,
            )),
            None,
            0,
        ),
        message(
            Some(tool(
                json!("read_file"),
                json!("child"),
                Some(json!(&binding)),
                1,
            )),
            None,
            1,
        ),
        message(
            Some(tool(json!("spawn_agent"), json!("child"), None, 2)),
            None,
            2,
        ),
        message(
            Some(tool(
                json!("spawn_agent"),
                json!("child"),
                Some(Value::Null),
                3,
            )),
            None,
            3,
        ),
        message(
            Some(tool(
                json!("followup_task"),
                json!("child"),
                Some(json!(session(43, "/synthetic/conflicting/session"))),
                4,
            )),
            None,
            4,
        ),
        message(None, Some(progress("child", Some(binding))), 5),
    ]);
    let rows = page.entries();
    assert_eq!(rows.len(), 6);
    let tools = |i: usize| rows[i].tool.as_ref().unwrap();
    assert!(decode(tools(0)).is_some());
    assert_eq!(find(rows, tools(0)), Some(5));
    assert_eq!(find(rows, tools(4)), None);
    assert_eq!(find(rows, tools(2)), Some(5));
    assert_eq!(find(rows, tools(3)), Some(5));
    measure(arm, "saved-child-link", || decode(black_box(tools(0))));
    measure(arm, "matching-live-overlay", || {
        find(black_box(rows), black_box(tools(0)))
    });
    measure(arm, "conflicting-live-overlay", || {
        find(black_box(rows), black_box(tools(4)))
    });
    measure(arm, "missing-binding", || {
        find(black_box(rows), black_box(tools(2)))
    });
    measure(arm, "null-binding", || {
        find(black_box(rows), black_box(tools(3)))
    });
    measure(arm, "non-task-tool", || {
        find(black_box(rows), black_box(tools(1)))
    });

    let expanded = session(112, "/synthetic/delegated/warm");
    let mut many = Transcript::default();
    let mut messages: Vec<_> = (0..24)
        .map(|i| {
            message(
                Some(tool(
                    json!("spawn_agent"),
                    json!(format!("pending-{i}")),
                    Some(json!(session(100 + i as u128, "/synthetic/delegated/warm"))),
                    i,
                )),
                None,
                i,
            )
        })
        .collect();
    messages.push(message(
        None,
        Some(progress("pending-12", Some(expanded))),
        24,
    ));
    many.reset(messages);
    assert_eq!(many.entries().len(), 25);
    let page = black_box(many.entries());
    assert_eq!(find(page, page[12].tool.as_ref().unwrap()), Some(24));
    measure(arm, "24-overlay-probes", || {
        page.iter()
            .filter_map(|entry| entry.tool.as_ref())
            .filter(|tool| find(page, black_box(tool)).is_some())
            .count()
    });
}

fn main() {
    let arm = std::env::args().nth(1).expect("arm");
    if arm == "parity" {
        parity();
    } else {
        allocations(&arm);
    }
}
