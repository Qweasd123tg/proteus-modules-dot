use super::{apply_patch, patch};
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
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static ALLOC: Counter = Counter;

#[test]
fn compare_apply_patch() {
    let workspace = PathBuf::from(std::env::var_os("CODEX_PATCH_FIXTURE").unwrap());
    let path = workspace.join("f");
    let out = PathBuf::from(std::env::var_os("CODEX_PATCH_OUTPUT").unwrap());
    let filler = "fn existing_call() { return 12345; }\n".repeat(4096);
    for (label, before, hunk, expected) in [
        (
            "exact",
            format!("{filler}target\n"),
            "@@\n-target\n+done",
            Some(format!("{filler}done\n")),
        ),
        (
            "rstrip",
            format!("{filler}target   \n"),
            "@@\n-target\n+done",
            Some(format!("{filler}done\n")),
        ),
        (
            "unicode_tail",
            format!("{filler}“target”—end\n"),
            "@@\n-\"target\"-end\n+done",
            Some(format!("{filler}done\n")),
        ),
        (
            "absent",
            filler.clone(),
            "@@\n-target: missing\n+done",
            None,
        ),
        (
            "prefix",
            "x—\nx—y z\nx—y\n".into(),
            "@@\n-x-y\n+done",
            Some("x—\nx—y z\ndone\n".into()),
        ),
        (
            "eof",
            "x—y\nx–y\n".into(),
            "@@\n-x-y\n+done\n*** End of File",
            Some("x—y\ndone\n".into()),
        ),
        (
            "eof_miss",
            "x—y\nother\n".into(),
            "@@\n-x-y\n+done\n*** End of File",
            None,
        ),
        (
            "strict_precedence",
            "x—y\n  x-y  \nx-y\n".into(),
            "@@\n-x-y\n+done",
            Some("x—y\n  x-y  \ndone\n".into()),
        ),
        (
            "multiline",
            "a—b\nx y suffix\na—b\n  x\u{a0}y \n".into(),
            "@@\n-a-b\n-x\u{2009}y\n+done",
            Some("a—b\nx y suffix\ndone\n".into()),
        ),
    ] {
        let input = patch(&format!("*** Update File: f\n{hunk}"));
        for pass in 0..3 {
            std::fs::write(&path, &before).unwrap();
            COUNT.with(|c| c.set(Some((0, 0))));
            let reply = apply_patch(&input, &workspace);
            let (calls, bytes) = COUNT.with(|c| c.take().unwrap());
            let after = std::fs::read(&path).unwrap();
            assert_eq!(reply.is_ok(), expected.is_some(), "{label}: {reply:?}");
            assert_eq!(
                after,
                expected.as_ref().unwrap_or(&before).as_bytes(),
                "{label}"
            );
            if pass == 0 {
                std::fs::write(out.join(format!("{label}.file")), &after).unwrap();
                std::fs::write(
                    out.join(format!("{label}.result")),
                    serde_json::to_vec(&reply).unwrap(),
                )
                .unwrap();
            }
            println!("COUNT {label} {pass} {calls} {bytes}");
        }
    }
}
