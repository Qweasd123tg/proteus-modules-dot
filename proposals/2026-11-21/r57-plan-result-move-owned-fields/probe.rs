// Test-only whole-invocation allocations for the stock/candidate differential.
use proteus_contracts::{
    contracts::ExecutionAttribution,
    domain::new_execution_id,
    process_module::{ProcessModuleError, ToolModule, ToolModuleHost, ToolModuleInvocationContext},
};
use serde_json::json;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    path::PathBuf,
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

struct Host;
impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
}

#[test]
fn whole_plan_tool_allocations() {
    let call = std::fs::read_to_string(std::env::var_os("R57_CALL").unwrap()).unwrap();
    let context = if std::env::var_os("R57_BAD_CONTEXT").is_some() {
        "{".to_owned()
    } else {
        serde_json::to_string(&ToolModuleInvocationContext {
            cwd: PathBuf::from("fixture-root"),
            skills: Default::default(),
            attribution: ExecutionAttribution::detached(new_execution_id()),
            config: json!({}),
        })
        .unwrap()
    };
    let tool = crate::PlanTool;
    drop(tool.invoke_json(call.clone(), context.clone(), &mut Host));
    let starting = LIVE.load(Relaxed);
    PEAK.store(starting, Relaxed);
    ACTIVE.store(true, Relaxed);
    let result = tool.invoke_json(call, context, &mut Host);
    ACTIVE.store(false, Relaxed);
    let peak = PEAK.load(Relaxed) - starting;
    let wire = result.unwrap_or_else(|e| format!("ERROR: {}", e.message));
    std::fs::write(std::env::var_os("R57_OUT").unwrap(), wire).unwrap();
    println!(
        "R57 {} {} {}",
        REQUESTED.load(Relaxed),
        CALLS.load(Relaxed),
        peak
    );
}
