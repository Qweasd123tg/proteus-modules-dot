use super::*;
use proteus_contracts::{
    contracts::ExecutionAttribution, domain::new_execution_id, process_module::ToolModuleHost,
};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    path::PathBuf,
    sync::atomic::{AtomicBool, AtomicU64, Ordering},
    time::Instant,
};

struct Meter;
static MEASURE: AtomicBool = AtomicBool::new(false);
static BYTES: AtomicU64 = AtomicU64::new(0);
static CALLS: AtomicU64 = AtomicU64::new(0);

fn count(ptr: *mut u8, size: usize) -> *mut u8 {
    if !ptr.is_null() && MEASURE.load(Ordering::Relaxed) {
        CALLS.fetch_add(1, Ordering::Relaxed);
        BYTES.fetch_add(size as u64, Ordering::Relaxed);
    }
    ptr
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        count(unsafe { System.alloc(layout) }, layout.size())
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        count(unsafe { System.alloc_zeroed(layout) }, layout.size())
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        count(unsafe { System.realloc(ptr, layout, size) }, size)
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
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
fn measure_git_tool() {
    let cwd = PathBuf::from(std::env::var_os("R47_CWD").unwrap());
    let name = std::env::var("R47_NAME").unwrap();
    let args: Value = serde_json::from_str(&std::env::var("R47_ARGS").unwrap()).unwrap();
    let call = json!({"id": "bench", "name": name, "args": args}).to_string();
    let context = serde_json::to_string(&ToolModuleInvocationContext {
        cwd,
        skills: Default::default(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        config: json!({}),
    })
    .unwrap();
    let tool: &dyn ToolModule = match name.as_str() {
        "git_status" => &GitStatusTool,
        "git_diff" => &GitDiffTool,
        _ => panic!("unsupported fixture"),
    };

    let clock = Instant::now();
    MEASURE.store(true, Ordering::SeqCst);
    let result = tool.invoke_json(call, context, &mut Host);
    MEASURE.store(false, Ordering::SeqCst);
    let ns = clock.elapsed().as_nanos();
    let bytes = BYTES.load(Ordering::Relaxed);
    let calls = CALLS.load(Ordering::Relaxed);
    std::fs::write(std::env::var_os("R47_OUT").unwrap(), result.unwrap()).unwrap();
    println!("R47 {bytes} {calls} {ns}");
}
