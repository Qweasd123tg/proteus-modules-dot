// Test-only whole-invocation probes. reproduce.py removes the allocator
// attribute in separate, system-allocated wall-clock binaries.
use proteus_contracts::{
    contracts::{ExecutionAttribution, ProcessContextProviderInput, ProcessContextProviderRequest},
    domain::{AgentTask, SkillRuntimeSettings, ToolCall, new_execution_id},
    process_module::{
        ContextProviderModule, ProcessModuleError, ToolModule, ToolModuleHost,
        ToolModuleInvocationContext,
    },
};
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    path::PathBuf,
    sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
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

struct Host;
impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
}

#[test]
fn skill_invocation() {
    let fixture: Value =
        serde_json::from_slice(&std::fs::read(std::env::var_os("R54_FIXTURE").unwrap()).unwrap())
            .unwrap();
    let loops = std::env::var("R54_LOOPS")
        .unwrap()
        .parse::<usize>()
        .unwrap();
    let cwd = PathBuf::from(fixture["cwd"].as_str().unwrap());
    let skills: SkillRuntimeSettings = serde_json::from_value(fixture["settings"].clone()).unwrap();
    let attribution = ExecutionAttribution::detached(new_execution_id());
    let is_provider = fixture["provider"].as_bool().unwrap_or(false);
    let (call, context) = if is_provider {
        (
            serde_json::to_string(&ProcessContextProviderRequest {
                input: ProcessContextProviderInput {
                    provider_id: "skills".into(),
                    task: AgentTask::new("load skill", cwd),
                    metadata: Value::Null,
                },
                attribution,
                skills,
            })
            .unwrap(),
            String::new(),
        )
    } else {
        (
            serde_json::to_string(&ToolCall::new(
                "bench",
                "skill",
                json!({"name": fixture["name"]}),
            ))
            .unwrap(),
            serde_json::to_string(&ToolModuleInvocationContext {
                cwd,
                skills,
                attribution,
                config: json!({}),
            })
            .unwrap(),
        )
    };
    let invoke = |input, context| {
        if is_provider {
            crate::SkillsContextProvider.provide_json(input)
        } else {
            crate::SkillTool.invoke_json(input, context, &mut Host)
        }
    };
    drop(invoke(call.clone(), context.clone()));
    let mut total_ns = 0;
    let mut peak = 0;
    for i in 0..loops {
        let input = call.clone();
        let cx = context.clone();
        let base_live = LIVE.load(Relaxed);
        PEAK.store(base_live, Relaxed);
        ACTIVE.store(true, Relaxed);
        let start = Instant::now();
        let result = invoke(input, cx);
        total_ns += start.elapsed().as_nanos();
        ACTIVE.store(false, Relaxed);
        peak = peak.max(PEAK.load(Relaxed) - base_live);
        if i + 1 == loops {
            let wire = result.unwrap_or_else(|error| format!("ERROR: {}", error.message));
            std::fs::write(std::env::var_os("R54_OUT").unwrap(), wire).unwrap();
        }
    }
    println!(
        "R54 {} {} {} {}",
        REQUESTED.load(Relaxed) / loops,
        CALLS.load(Relaxed) / loops,
        peak,
        total_ns / loops as u128
    );
}
