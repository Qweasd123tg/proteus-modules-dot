// Scratch-only real skill invocation and allocator checks.
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

struct FixtureHost;
impl proteus_contracts::process_module::ToolModuleHost for FixtureHost {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
}

#[test]
#[ignore = "differential probe requires fixture environment"]
fn allocation_case() {
    use proteus_contracts::{contracts::ExecutionAttribution, domain::new_execution_id};
    let case = std::env::var("R65_CASE").unwrap();
    let (skill, args, disabled) = match case.as_str() {
        "small" => ("skill", json!({"name":"review"}), vec![]),
        "large" => ("skill", json!({"name":"large"}), vec![]),
        "empty" => ("skill", json!({"name":"blank"}), vec![]),
        "crlf" => ("skill", json!({"name":"windows"}), vec![]),
        "missing" => ("skill", json!({"name":"missing"}), vec![]),
        "disabled" => ("skill", json!({"name":"review"}), vec!["review".into()]),
        "bad-args" => ("skill", json!({"name":42}), vec![]),
        "wrong-tool" => ("other", json!({"name":"review"}), vec![]),
        _ => panic!("unknown fixture: {case}"),
    };
    let context = serde_json::to_string(&ToolModuleInvocationContext {
        cwd: std::env::var_os("R65_CWD").unwrap().into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: SkillRuntimeSettings {
            disabled,
            packages: vec![],
        },
        config: Value::Null,
    })
    .unwrap();
    let call = json!({"id":"call-ю","name":skill,"args":args}).to_string();
    drop(
        SkillTool
            .invoke_json(call.clone(), context.clone(), &mut FixtureHost)
            .unwrap(),
    );
    let start = LIVE.load(Relaxed);
    PEAK.store(start, Relaxed);
    ACTIVE.store(true, Relaxed);
    let result = SkillTool
        .invoke_json(call, context, &mut FixtureHost)
        .unwrap();
    ACTIVE.store(false, Relaxed);
    let peak = PEAK.load(Relaxed) - start;
    std::fs::write(std::env::var_os("R65_WIRE").unwrap(), result).unwrap();
    println!(
        "R65 {} {} {}",
        REQUESTED.load(Relaxed),
        CALLS.load(Relaxed),
        peak
    );
}
