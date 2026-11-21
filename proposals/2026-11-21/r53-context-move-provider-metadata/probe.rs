// Test-only whole-invocation probes. reproduce.py removes the allocator
// attribute in separate, system-allocated wall-clock binaries.
use proteus_contracts::{
    contracts::ExecutionAttribution,
    domain::{AgentTask, new_execution_id},
    process_module::{
        ContextBuilderModule, ContextBuilderModuleHost, ContextBuilderModuleInput,
        ProcessModuleError, ProcessModuleResult,
    },
};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    collections::BTreeMap,
    path::PathBuf,
    sync::{
        Mutex,
        atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
    },
    time::Instant,
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

struct ProviderHost {
    replies: BTreeMap<String, String>,
    tracing: AtomicBool,
    trace: Mutex<Vec<(String, String)>>,
}

impl ContextBuilderModuleHost for ProviderHost {
    fn context_provider_json(
        &self,
        provider: String,
        input: String,
    ) -> ProcessModuleResult<String> {
        let value = self
            .replies
            .get(&provider)
            .unwrap_or_else(|| panic!("unexpected provider {provider}"));
        if self.tracing.load(Relaxed) {
            self.trace.lock().unwrap().push((provider, input));
        }
        match value.strip_prefix("ERROR: ") {
            Some(message) => Err(ProcessModuleError::new(message)),
            None => Ok(value.clone()),
        }
    }
}

#[test]
fn context_build_invocation() {
    let fixture: Value =
        serde_json::from_slice(&std::fs::read(std::env::var_os("R53_FIXTURE").unwrap()).unwrap())
            .unwrap();
    let loops = std::env::var("R53_LOOPS")
        .unwrap()
        .parse::<usize>()
        .unwrap();
    let input = serde_json::to_string(&ContextBuilderModuleInput {
        task: AgentTask::new("needle", PathBuf::from("fixture-root")),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        config: fixture["config"].clone(),
    })
    .unwrap();
    let mut host = ProviderHost {
        replies: serde_json::from_value(fixture["providers"].clone()).unwrap(),
        tracing: AtomicBool::new(false),
        trace: Mutex::new(Vec::new()),
    };
    let builder: Box<dyn ContextBuilderModule> = match fixture["builder"].as_str().unwrap() {
        "repo" => Box::new(crate::RepoAwareContextBuilderModule),
        "codex" => Box::new(crate::CodexContextBuilderModule),
        _ => unreachable!(),
    };
    drop(builder.build_json(input.clone(), &mut host));

    let mut total_ns = 0;
    let mut peak = 0;
    for _ in 0..loops {
        let call = input.clone();
        let base_live = LIVE.load(Relaxed);
        PEAK.store(base_live, Relaxed);
        ACTIVE.store(true, Relaxed);
        let start = Instant::now();
        let result = builder.build_json(call, &mut host);
        total_ns += start.elapsed().as_nanos();
        ACTIVE.store(false, Relaxed);
        peak = peak.max(PEAK.load(Relaxed) - base_live);
        drop(result);
    }
    // Capture callback frame bytes and whole reply/error only after the meter is off.
    host.tracing.store(true, Relaxed);
    let wire = builder
        .build_json(input, &mut host)
        .unwrap_or_else(|e| format!("ERROR: {}", e.message));
    let trace = host.trace.into_inner().unwrap();
    std::fs::write(
        std::env::var_os("R53_OUT").unwrap(),
        json!({"wire": wire, "trace": trace}).to_string(),
    )
    .unwrap();
    println!(
        "R53 {} {} {} {}",
        REQUESTED.load(Relaxed) / loops,
        CALLS.load(Relaxed) / loops,
        peak,
        total_ns / loops as u128
    );
}
