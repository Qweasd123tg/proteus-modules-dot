// Temporary counting allocator and main added only to the benchmark build.
mod measure {
    use super::*;
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

    struct Meter;
    #[global_allocator]
    static METER: Meter = Meter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);

    fn record(size: usize) {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(size, Relaxed);
    }

    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            let p = unsafe { System.alloc(layout) };
            if !p.is_null() { record(layout.size()); }
            p
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) };
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            let new = unsafe { System.realloc(p, layout, size) };
            if !new.is_null() { record(size); }
            new
        }
    }

    pub fn run() {
        let mode = std::env::args().nth(1).unwrap();
        let full = "abc1234000000000000000000000000000000000";
        let short = "abc1234";
        let mut host = Host::default(); // no server: any unintended cache miss fails validation below
        for (size, count, commit_b, diff_b) in [
            ("small", 1, 256, 256),
            ("medium", 24, 24 * 1024, 3 * 1024),
            ("large", 160, 480 * 1024, 192 * 1024),
        ] {
            let mut git = Git::default();
            git.graph = Some(Log {
                more: false,
                entries: vec![json!({"hash":full,"short":short,"summary":"Change","parents":[]})],
            });
            git.commit = Some(full.into());
            let files: Vec<_> = (0..count).map(|index| json!({
                "path":format!("src/test{index}.rs"), "status":"modified",
                "original":null, "added":1, "deleted":0
            })).collect();
            let path = files[0].str("path").to_owned();
            let mut patch = "+ changed line\n".repeat(commit_b / 15 + 1);
            patch.truncate(commit_b);
            let mut selected = "- before\n+ after\n".repeat(diff_b / 17 + 1);
            selected.truncate(diff_b);
            assert_eq!((patch.len(), selected.len()), (commit_b, diff_b));
            let commit = Arc::new(json!({"hash":full,"short":short,
                "parents":[], "summary":"Подготовить тест","files":files,"patch":patch}));
            let diff = Arc::new(json!({
                "path":path,"kind":"text","patch":selected,"revision":null
            }));
            let (w_commit,w_diff) = (Arc::downgrade(&commit),Arc::downgrade(&diff));
            git.history_cache.insert_commit(short, commit);
            git.history_cache.insert_diff(full,&path,diff);
            for (view, doc) in [
                ("inspector", Document::Graph),
                ("commit", Document::Commit(short.into())),
                ("file", Document::Commit(short.into())),
            ] {
                if view == "file" { git.commit_files.insert(short.into(), path.clone()); }
                CALLS.store(0, Relaxed);
                BYTES.store(0, Relaxed);
                let root = git.document(&host, &doc);
                let calls = CALLS.load(Relaxed);
                let bytes = BYTES.load(Relaxed);
                let wire = root.to_string();
                if view == "inspector" {
                    assert!(wire.contains("commit-detail-files") && wire.contains("Подготовить тест"));
                } else {
                    assert!(wire.contains("commit-patch"));
                    assert!(wire.contains(if view == "file" { "- before" } else { "+ changed line" }));
                }
                if mode == "wire" {
                    println!("{wire}");
                } else {
                    assert_eq!(mode, "measure");
                    println!("{size} {view} {count} {commit_b} {diff_b} {} {calls} {bytes}", wire.len());
                }
            }
            // No returned widget or caller state owns either snapshot after render.
            assert_eq!((w_commit.strong_count(),w_diff.strong_count()), (1,1));
            git.session_changed(&mut host);
            assert!(w_commit.upgrade().is_none() && w_diff.upgrade().is_none());
        }
    }
}
fn main() { measure::run(); }
