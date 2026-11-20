use super::*;
use proteus_contracts::{
    contracts::{ExecutionAttribution, ProcessContextProviderInput, ProcessContextProviderRequest},
    domain::{AgentTask, ToolCall, new_execution_id},
    process_module::{
        ContextProviderModule, ProcessModuleResult, ToolModule, ToolModuleHost,
        ToolModuleInvocationContext,
    },
};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    hint::black_box,
};

thread_local! { static COUNTERS: Cell<Option<(usize, usize)>> = const { Cell::new(None) }; }

struct ProbeAlloc;
impl ProbeAlloc {
    fn count(bytes: usize) {
        let _ = COUNTERS.try_with(|c| {
            if let Some((requests, sum)) = c.get() {
                c.set(Some((requests + 1, sum + bytes)));
            }
        });
    }
}
unsafe impl GlobalAlloc for ProbeAlloc {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        Self::count(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        Self::count(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        Self::count(size);
        unsafe { System.realloc(ptr, layout, size) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}
#[global_allocator]
static ALLOC: ProbeAlloc = ProbeAlloc;

struct Host(bool);
impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> ProcessModuleResult<bool> {
        Ok(self.0)
    }
}

#[test]
fn measure_recall_and_snapshot_exports() {
    let dir = tempfile::tempdir().unwrap();
    let good = Arc::new(JsonlMemoryStoreModule::new(dir.path().join("valid.jsonl")));
    let literal = "кириллица🙂\n\"quote\"\\\0\u{7f}";
    for item in [
        MemoryItem::new("fact", format!("one {literal}"), json!({"order": 1})),
        MemoryItem::new("preference", "not a match", json!({"order": 2})),
        MemoryItem::new("fact", format!("three {literal}"), json!({"order": 3})),
    ] {
        good.remember(&item).unwrap();
    }
    let bad_path = dir.path().join("bad.jsonl");
    fs::write(&bad_path, "malformed\n").unwrap();
    let bad = Arc::new(JsonlMemoryStoreModule::new(bad_path));
    let missing = Arc::new(JsonlMemoryStoreModule::new(
        dir.path().join("missing.jsonl"),
    ));
    let invoke = |metadata: Value, args: Value, store: &Arc<JsonlMemoryStoreModule>, cancel| {
        let provider = provider::MemoryProvider {
            store: store.clone(),
        };
        let tool = tools::MemoryTool {
            store: store.clone(),
            remember: false,
        };
        let attribution = ExecutionAttribution::detached(new_execution_id());
        let req = ProcessContextProviderRequest {
            input: ProcessContextProviderInput {
                provider_id: "jsonl_memory".into(),
                task: AgentTask::new("recall", dir.path().to_path_buf()),
                metadata,
            },
            attribution: attribution.clone(),
            skills: Default::default(),
        };
        let call = ToolCall::new("call_probe", "recall_memory", args);
        let tool_ctx = ToolModuleInvocationContext {
            cwd: dir.path().to_path_buf(),
            attribution,
            config: Value::Null,
            skills: Default::default(),
        };
        let normalize = |r: ProcessModuleResult<String>| match r {
            Ok(payload) => json!({"ok":payload}),
            Err(error) => {
                json!({"error":error.message.replace(dir.path().to_str().unwrap(), "<fixture>")})
            }
        };
        (
            normalize(provider.provide_json(serde_json::to_string(&req).unwrap())),
            normalize(tool.invoke_json(
                serde_json::to_string(&call).unwrap(),
                serde_json::to_string(&tool_ctx).unwrap(),
                &mut Host(cancel),
            )),
        )
    };

    for (tag, metadata, args, store, cancel) in [
        (
            "unicode-only",
            json!({"text": literal, "limit":1}),
            json!({"query":literal, "limit":1}),
            &good,
            false,
        ),
        (
            "unicode-both",
            json!({"text": literal, "limit":usize::MAX}),
            json!({"query":literal, "limit":usize::MAX}),
            &good,
            false,
        ),
        (
            "empty-text",
            json!({"text":"","limit":3}),
            json!({"query":"","limit":3}),
            &good,
            false,
        ),
        (
            "zero-limit",
            json!({"text":literal,"limit":0}),
            json!({"query":literal,"limit":0}),
            &bad,
            false,
        ),
        (
            "not-found",
            json!({"text":literal,"limit":1}),
            json!({"query":literal,"limit":1}),
            &missing,
            false,
        ),
        (
            "wrong-query-type",
            json!({"text":11,"limit":1}),
            json!({"query":11,"limit":1}),
            &good,
            false,
        ),
        (
            "invalid-limit-default",
            json!({"text":literal,"limit":-1}),
            json!({"query":literal,"limit":-1}),
            &good,
            false,
        ),
        (
            "malformed-jsonl",
            json!({"text":literal,"limit":1}),
            json!({"query":literal,"limit":1}),
            &bad,
            false,
        ),
        (
            "cancelled",
            json!({"text":literal,"limit":1}),
            json!({"query":literal,"limit":1}),
            &bad,
            true,
        ),
    ] {
        let (provider, tool) = invoke(metadata, args, store, cancel);
        println!(
            "WIRE {}",
            json!({"tag":tag,"provider":provider,"tool":tool})
        );
    }
    for (shape, text) in [
        ("empty", String::new()),
        ("ascii_16", "x".repeat(16)),
        ("match_utf8_16", "one кирилл".to_owned()),
        ("ascii_4096", "x".repeat(4096)),
        ("escaped_65536", "\n\"\\\0".repeat(16384)),
    ] {
        for (path, store, limit) in [
            ("zero", &bad, 0),
            ("missing", &missing, 1),
            ("scan", &good, 2),
        ] {
            let query = MemoryQuery::new(text.clone(), limit);
            let _ = black_box(store.recall(black_box(&query)).unwrap());
            for repeat in 1..=3 {
                COUNTERS.with(|c| c.set(Some((0, 0))));
                let recalled = black_box(store.recall(black_box(&query)).unwrap());
                let (requests, bytes) = COUNTERS.with(|c| c.replace(None).unwrap());
                let expected = match (path, shape) {
                    ("scan", "empty") => 2,
                    ("scan", "match_utf8_16") => 1,
                    _ => 0,
                };
                assert_eq!(recalled.len(), expected);
                println!(
                    "ALLOC {path},{shape},{},{repeat},{requests},{bytes}",
                    text.len()
                );
            }
        }
    }
}
