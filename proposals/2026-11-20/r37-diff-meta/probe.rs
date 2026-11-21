use std::fmt::Write;
use std::hint::black_box;
#[cfg(not(count_alloc))]
use std::time::Instant;

#[cfg(count_alloc)]
mod alloc {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    pub struct Counter;
    #[global_allocator]
    static ALLOC: Counter = Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            unsafe { System.dealloc(ptr, layout) }
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(size, Relaxed);
            unsafe { System.realloc(ptr, layout, size) }
        }
    }
    pub fn counts() -> [usize; 2] {
        [CALLS.load(Relaxed), BYTES.load(Relaxed)]
    }
}

#[derive(Default)]
struct Case {
    patch: String,
    a: Vec<baseline::FileInfo>,
    b: Vec<candidate::FileInfo>,
}
impl Case {
    fn file(&mut self, p: &str, content: bool) {
        writeln!(self.patch, "diff --git a/{p} b/{p}").unwrap();
        if content {
            self.patch.push_str("@@ -2,1 +2,1 @@\n-old\n+new\n");
        }
    }
    fn meta(&mut self, p: &str, status: &str, msg: Option<&str>) {
        self.a.push(baseline::FileInfo {
            path: p.into(),
            status: status.into(),
            message: msg.map(str::to_owned),
        });
        self.b.push(candidate::FileInfo {
            path: p.into(),
            status: status.into(),
            message: msg.map(str::to_owned),
        });
    }
    fn compare(&self) {
        let a = baseline::parse(&self.patch, &self.a);
        let b = candidate::parse(&self.patch, &self.b);
        assert_eq!(a.len(), b.len());
        for (a, b) in a.iter().zip(&b) {
            assert_eq!(format!("{a:?}"), format!("{b:?}"));
        }
    }
    fn run(&self, b: bool) {
        if b {
            black_box(candidate::parse(black_box(&self.patch), black_box(&self.b)));
        } else {
            black_box(baseline::parse(black_box(&self.patch), black_box(&self.a)));
        }
    }
}

fn randomized() {
    let mut state = 67679u64;
    let mut draw = |n| {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
        ((state >> 32) % n) as usize
    };
    let paths = [
        "",
        "Changes",
        "f",
        "F",
        "ß",
        "./x",
        "src/input.rs",
        "old input",
    ];
    for i in 0..512 {
        let mut c = Case::default();
        for _ in 0..draw(20) {
            c.file(paths[draw(8)], draw(2) == 0);
        }
        for _ in 0..[0, 1, 2, 16, 31, 32, 33, 63, 64, 65, 127, 128, 129, 256][i % 14] {
            c.meta(
                paths[draw(8)],
                ["", "modified", "added", "binary"][draw(4)],
                [None, Some(""), Some("big"), Some("notice")][draw(4)],
            );
        }
        c.compare();
    }
}

fn measure(label: &str, c: &Case, reps: usize) {
    c.compare();
    c.run(false);
    c.run(true);
    #[cfg(count_alloc)]
    {
        let _ = reps;
        let mut v = [[0; 2]; 2];
        for i in [0, 1] {
            let start = alloc::counts();
            c.run(i == 1);
            let end = alloc::counts();
            v[i] = [end[0] - start[0], end[1] - start[1]];
        }
        println!(
            "{label}: requests / requested bytes {:?} => {:?}",
            v[0], v[1]
        );
    }
    #[cfg(not(count_alloc))]
    {
        let mut values = [Vec::new(), Vec::new()];
        for round in 0..11 {
            for i in [round % 2, 1 - round % 2] {
                let start = Instant::now();
                for _ in 0..reps {
                    c.run(i == 1);
                }
                values[i].push(start.elapsed().as_nanos() / reps as u128);
            }
        }
        for v in &mut values {
            v.sort_unstable();
        }
        println!(
            "{label}: ns/parse+drop {} => {}; speedup {:.2}x (median of 11; {reps} parses/sample)",
            values[0][5],
            values[1][5],
            values[0][5] as f64 / values[1][5] as f64
        );
    }
}
fn main() {
    randomized();
    println!("512 mixed full-output comparisons passed");
    for n in [1, 8, 32, 64, 128, 129, 256, 1024, 4096] {
        for mode in ["meta-only", "paired-reverse"] {
            let mut c = Case::default();
            for i in 0..n {
                if mode == "paired-reverse" {
                    c.file(&format!("src/dir/file-{i:06}.rs"), false);
                }
                c.meta(
                    &format!("src/dir/file-{:06}.rs", n - 1 - i),
                    "modified",
                    Some("oversize"),
                );
            }
            measure(
                &format!("{n} {mode}"),
                &c,
                if n <= 64 {
                    200
                } else if n < 1024 {
                    25
                } else {
                    1
                },
            );
        }
    }
    let mut c = Case::default();
    for i in 0..100 {
        c.file(&format!("f{i}"), true);
    }
    measure("100 patch cards without metadata", &c, 80);
    c.meta("f99", "modified", None);
    measure("100 patch cards / 1 metadata", &c, 80);
}
