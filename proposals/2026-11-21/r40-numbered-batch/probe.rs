use super::*;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    path::PathBuf,
};

struct Counter;
thread_local! { static COUNT: Cell<Option<(usize, usize)>> = const { Cell::new(None) }; }
fn count(bytes: usize) {
    COUNT.with(|c| {
        if let Some((n, total)) = c.get() {
            c.set(Some((n + 1, total + bytes)));
        }
    });
}
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        count(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        count(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        count(n);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) { unsafe { System.dealloc(p, l) } }
}
#[global_allocator]
static ALLOC: Counter = Counter;

#[test]
fn compare_read_many() {
    let dir = PathBuf::from(std::env::var_os("READ_MANY_WORKSPACE").unwrap());
    let ctx = ToolModuleInvocationContext {
        skills: Default::default(), cwd: dir.clone(),
        attribution: ExecutionAttribution::detached(new_execution_id()), config: Value::Null,
    };
    let cases = [
        ("empty", vec![], true, 1000),
        ("one_line", vec![b'x'; 64 * 1024], true, 102400),
        ("small", b"first\r\nsecond\nlast".to_vec(), true, 1024),
        ("short_lines", b"x\n".repeat(12_000), true, 204800),
        ("budget_cut", b"\n".repeat(65536), true, 65544),
        ("utf8_cut", "\n\n\nаб😀".as_bytes().to_vec(), true, 24),
        ("unnumbered", b"x\n".repeat(12_000), false, 204800),
        ("bad_utf8", [vec![b'\n'; 256], vec![0xff]].concat(), true, 270),
    ];
    for (label, data, numbered, budget) in cases {
        std::fs::write(dir.join("f"), &data).unwrap();
        for pass in 0..3 {
            let call = json!({"id":"compare","name":"read_many_files","args":{
                "paths":["f"], "line_numbers":numbered,"max_bytes_total":budget,"max_bytes_per_file":102400
            }}).to_string();
            let context = serde_json::to_string(&ctx).unwrap();
            COUNT.with(|c| c.set(Some((0,0))));
            let result = ReadManyFilesTool.invoke_json(call, context, &mut TestToolHost).unwrap();
            let (n, bytes) = COUNT.with(|c| c.take().unwrap());
            println!("COUNT {label} {pass} {n} {bytes}");
            let reply: Value = serde_json::from_str(&result).unwrap();
            assert_eq!(reply["ok"], label != "bad_utf8");
            if pass == 0 {
                println!("WIRE {label} {result}");
            }
        }
    }
}
