// Scratch-only paired context builder and host callback checks.
use super::*;
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

struct FixtureHost {
    response: String,
    tracing: bool,
    trace: std::sync::Mutex<Vec<(String, String)>>,
}

impl proteus_contracts::process_module::ContextBuilderModuleHost for FixtureHost {
    fn context_provider_json(
        &self,
        provider: String,
        request: String,
    ) -> Result<String, ProcessModuleError> {
        if self.tracing {
            self.trace.lock().unwrap().push((provider, request));
        }
        Ok(self.response.clone())
    }
}

#[test]
#[ignore = "differential probe requires fixture environment"]
fn allocation_case() {
    use proteus_contracts::{
        contracts::ExecutionAttribution,
        domain::{AgentTask, new_execution_id},
    };
    let case = std::env::var("R66_CASE").unwrap();
    let strings = |prefix: &str, n: usize| {
        (0..n)
            .map(|i| format!("{prefix}-{i:03}-{}", "текст".repeat(10)))
            .collect::<Vec<_>>()
    };
    let repo_rich = || {
        json!({
            "providers":["fixture_first","fixture_second"],
            "manifest_files":strings("manifest",48),
            "project_instruction_files":strings("docs",48),
            "repo_tree_skip_entries":strings("skip",96),
            "max_search_results":0,"max_context_bytes":32000,
        })
    };
    let (builder, config): (&dyn ContextBuilderModule, Value) = match case.as_str() {
        "simple-null" => (&SimpleContextBuilderModule, Value::Null),
        "simple-empty" => (&SimpleContextBuilderModule, json!({})),
        "simple-custom" => (
            &SimpleContextBuilderModule,
            json!({
                "search_provider":"fixture_search","max_search_results":7,"memory_provider":"fixture_memory",
            }),
        ),
        "repo-small" => (
            &RepoAwareContextBuilderModule,
            json!({"providers":["fixture_first"]}),
        ),
        "repo-rich" => (&RepoAwareContextBuilderModule, repo_rich()),
        "codex-rich" => {
            let mut config = repo_rich();
            config["project_doc_max_bytes"] = 18000.into();
            config["git_diff_max_bytes"] = 14000.into();
            (&CodexContextBuilderModule, config)
        }
        "repo-unknown" => (
            &RepoAwareContextBuilderModule,
            json!({
                "providers":["fixture_first"],"bogus":strings("unused",24),
            }),
        ),
        "codex-bad-type" => (&CodexContextBuilderModule, json!({"providers":true})),
        _ => panic!("unknown fixture: {case}"),
    };
    let input = serde_json::to_string(&ContextBuilderModuleInput {
        task: AgentTask::new("inspect synthetic note 🦀", PathBuf::from("fixture-root")),
        config,
        attribution: ExecutionAttribution::detached(new_execution_id()),
    })
    .unwrap();
    let mut host = FixtureHost {
        response: serde_json::to_string(&vec![
            ContextChunk::new("fixture", "Result for note.").with_score(0.6),
        ])
        .unwrap(),
        tracing: false,
        trace: Default::default(),
    };
    drop(builder.build_json(input.clone(), &mut host));
    let measure = input.clone();
    let start = LIVE.load(Relaxed);
    PEAK.store(start, Relaxed);
    ACTIVE.store(true, Relaxed);
    let result = builder.build_json(measure, &mut host);
    ACTIVE.store(false, Relaxed);
    let peak = PEAK.load(Relaxed) - start;
    host.tracing = true;
    let wire = |result: Result<String, ProcessModuleError>| {
        result.unwrap_or_else(|e| format!("ERROR: {}", e.message))
    };
    let traced = wire(builder.build_json(input, &mut host));
    assert_eq!(wire(result), traced);
    let reply = json!({"body":traced, "trace":host.trace.into_inner().unwrap()}).to_string();
    std::fs::write(std::env::var_os("R66_WIRE").unwrap(), reply).unwrap();
    println!(
        "R66 {} {} {}",
        REQUESTED.load(Relaxed),
        CALLS.load(Relaxed),
        peak
    );
}
