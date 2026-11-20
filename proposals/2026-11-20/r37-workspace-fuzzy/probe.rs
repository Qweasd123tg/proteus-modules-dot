extern crate self as proteus_contracts;
pub mod git_support;
mod sessions;
mod workspace;
mod http_tests {
    mod workspace_git;
}
use std::{
    alloc::{GlobalAlloc, Layout, System},
    fs,
    path::Path,
    process::Command,
    sync::atomic::{AtomicUsize, Ordering::Relaxed},
};
use workspace::{after, before};
struct Count;
static N: AtomicUsize = AtomicUsize::new(0);
static B: AtomicUsize = AtomicUsize::new(0);
fn add(bytes: usize) {
    N.fetch_add(1, Relaxed);
    B.fetch_add(bytes, Relaxed);
}
unsafe impl GlobalAlloc for Count {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        add(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        add(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        add(n);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static ALLOCATOR: Count = Count;

#[test]
fn scalar_scores_match_reference() {
    let atoms = [
        "A", "a", ".", "Ж", "/", "_", "İ", "\u{307}", "Σ", "ς", "🙂", "Я",
    ];
    let mut paths = Vec::new();
    for a in atoms {
        for b in atoms {
            for c in atoms {
                paths.push(format!("{a}{b}{c}"));
            }
        }
    }
    let mut queries: Vec<String> = vec!["".into(), "a Σ".into(), "И İ 🙂".into(), "  Я\tЖ ".into()];
    queries.extend(
        atoms
            .iter()
            .flat_map(|a| atoms.iter().map(move |b| format!("{a}{b}"))),
    );
    for q in &queries {
        assert_eq!(
            before::score_matrix(q, &paths),
            after::score_matrix(q, &paths),
            "{q}"
        );
    }
    println!(
        "scalar equivalence: {} queries × {} paths",
        queries.len(),
        paths.len()
    );
}

fn git(root: &Path, args: &[&str]) {
    assert!(
        Command::new("git")
            .current_dir(root)
            .args(args)
            .status()
            .unwrap()
            .success()
    );
}
#[test]
fn real_git_and_walk_search() {
    let root = tempfile::tempdir().unwrap();
    let p = root.path();
    fs::create_dir(p.join("target")).unwrap();
    fs::create_dir(p.join("Source")).unwrap();
    fs::write(p.join(".gitignore"), "target/\n").unwrap();
    fs::write(p.join("target/ignored-needle"), "").unwrap();
    for i in 0..4096 {
        fs::write(p.join(format!("Source/文件-{i:04}-Ж_Я-needle.txt")), "").unwrap();
    }
    for git_index in [false, true] {
        if git_index {
            git(p, &["init", "-q"]);
            let gone = p.join("Source/deleted-π");
            fs::write(&gone, "").unwrap();
            git(p, &["add", "Source/deleted-π"]);
            fs::remove_file(gone).unwrap();
        }
        for q in [
            "not-found",
            "文件 ЖЯ",
            "source needle TXT",
            "🙂",
            "4095",
            "ignored",
            "deleted-π",
            "",
        ] {
            let qv = q.to_owned();
            let mut expected = None;
            for (round, a) in ["before", "after", "after", "before"]
                .into_iter()
                .enumerate()
            {
                let input = qv.clone(); // outside the measurement
                let n = N.load(Relaxed);
                let b = B.load(Relaxed);
                // Stop counters before converting to JSON or inspecting results.
                let (n, b, value) = if a == "before" {
                    let result = before::search(p, input).unwrap();
                    (
                        N.load(Relaxed) - n,
                        B.load(Relaxed) - b,
                        serde_json::to_value(result).unwrap(),
                    )
                } else {
                    let result = after::search(p, input).unwrap();
                    (
                        N.load(Relaxed) - n,
                        B.load(Relaxed) - b,
                        serde_json::to_value(result).unwrap(),
                    )
                };
                let entries = value["entries"].as_array().unwrap();
                assert_eq!(value["query"], q);
                match q {
                    "deleted-π" | "not-found" | "🙂" => assert!(entries.is_empty()),
                    "ignored" => assert_eq!(entries.len(), if git_index { 0 } else { 1 }),
                    "4095" => assert_eq!(entries.len(), 1),
                    _ => {
                        assert_eq!(entries.len(), 200);
                        assert_eq!(value["truncated"], true);
                    }
                }
                if let Some(old) = &expected {
                    assert_eq!(&value, old);
                } else {
                    expected = Some(value);
                }
                println!("measure,{git_index},{q},{round},{a},{n},{b}");
            }
        }
    }
}
