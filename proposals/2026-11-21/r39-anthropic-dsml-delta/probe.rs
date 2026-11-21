#![allow(dead_code)]
mod after;
mod before;

use std::{
    alloc::{GlobalAlloc, Layout, System},
    hint::black_box,
    sync::atomic::{AtomicUsize, Ordering::Relaxed},
};

struct Meter;
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
#[global_allocator]
static GLOBAL: Meter = Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(layout.size(), Relaxed);
        unsafe { System.alloc(layout) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(size, Relaxed);
        unsafe { System.realloc(p, layout, size) }
    }
}
fn counts() -> (usize, usize) {
    (CALLS.load(Relaxed), BYTES.load(Relaxed))
}
const OPEN: &str = "<｜｜DSML｜｜tool_calls>";
const CLOSE: &str = "</｜｜DSML｜｜tool_calls>";
fn check(chunks: &[&str]) {
    let mut a = before::DsmlStreamFilter::default();
    let mut b = after::DsmlStreamFilter::default();
    for (n, chunk) in chunks.iter().enumerate() {
        assert_eq!(a.filter(chunk), b.filter(chunk), "delta #{n}: {chunks:?}");
    }
    assert_eq!(a.finish(), b.finish(), "finish: {chunks:?}");
    // A finished block can be reused; neither raw marker nor hidden state is retained.
    assert_eq!(b.filter("new text"), "new text");
    assert_eq!(b.finish(), "");
}
fn main() {
    let strings = [
        "",
        "plain ∑界",
        "before <｜｜DSML｜｜tool_calls>secret\n🌍</｜｜DSML｜｜tool_calls> after",
        "before <｜｜DSML｜｜invoke name=\"x\">visible</｜｜DSML｜｜invoke> after",
        "<｜｜DSML｜｜tool_calls>hidden with </ broken<｜｜DSML｜｜tool_calls>",
        "literal < and </ and << and <｜ and </｜｜DSXX and 1 < 2",
        "pending <｜｜DSML｜｜inv",
        "pending <｜｜DS",
        "<｜｜DSML｜｜tool_calls>orphan</｜｜DS",
        "A</｜｜DSML｜｜invoke>B<｜｜DSML｜｜tool_calls>C</｜｜DSML｜｜tool_calls>D<",
    ];
    let mut exhaustive = 0;
    for s in strings {
        let boundaries: Vec<_> = s.char_indices().map(|(i, _)| i).chain([s.len()]).collect();
        for (i, &x) in boundaries.iter().enumerate() {
            for &y in &boundaries[i..] {
                check(&[&s[..x], &s[x..y], &s[y..]]);
                exhaustive += 1;
            }
        }
        let pieces: Vec<_> = boundaries.windows(2).map(|w| &s[w[0]..w[1]]).collect();
        check(&pieces);
    }
    let units = [
        "",
        " ",
        "abc",
        "界🙂",
        "<",
        "</",
        "｜",
        "<｜",
        "｜DSML",
        "｜｜",
        "DSML",
        "tool_calls>",
        ">",
        "hidden",
        OPEN,
        CLOSE,
        "<｜｜DSML｜｜",
        "</｜｜DSML｜｜",
        "invoke>",
        "\r\n",
        "a<b",
    ];
    let mut rng = 542555249_u64;
    for _ in 0..4096 {
        let seq: Vec<_> = (0..24)
            .map(|_| {
                rng = rng.wrapping_mul(6364136223846793005).wrapping_add(1);
                units[(rng >> 32) as usize % units.len()]
            })
            .collect();
        check(&seq);
    }
    // Check the externally important safety property against explicit expectations, too.
    let mut b = after::DsmlStreamFilter::default();
    for (d, expected) in [
        ("A<", "A"),
        ("｜｜DSML｜｜tool_calls>", ""),
        ("secret", ""),
        ("", ""),
        ("</｜", ""),
        ("｜DSML｜｜tool_calls>B", "B"),
        (" visible ", " visible "),
    ] {
        assert_eq!(b.filter(d), expected, "{d:?}");
    }
    assert_eq!(b.finish(), "");
    println!(
        "Parity: {exhaustive} three-way UTF-8 splits; 10 scalar-chunk traces; 4096 deterministic 24-delta traces; reset and explicit suppression verified"
    );
    println!(
        "case,delta_count,before_calls,after_calls,before_requested_bytes,after_requested_bytes"
    );
    for (case, initial, pattern) in [
        ("plain", "", &["Пример 🌍", " token", "\n", "abc xyz"][..]),
        (
            "hidden",
            OPEN,
            &["Пример 🌍", " token", "\n", "abc xyz"][..],
        ),
        ("literal_lt", "", &["1 < 2", "T<U>", "x <= y", "<tag>"][..]),
        (
            "mixed",
            "",
            &[
                "start<",
                "｜｜DSML｜｜tool_calls>",
                "hidden",
                "</｜",
                "｜DSML｜｜tool_calls>",
                "ok",
            ][..],
        ),
    ] {
        macro_rules! measure {
            ($v:ident) => {{
                let mut f = $v::DsmlStreamFilter::default();
                drop(f.filter(initial));
                let start = counts();
                for i in 0..4096 {
                    drop(black_box(f.filter(black_box(pattern[i % pattern.len()]))));
                }
                let end = counts();
                (end.0 - start.0, end.1 - start.1)
            }};
        }
        let a = measure!(before);
        let b = measure!(after);
        assert_eq!(b, measure!(after));
        assert_eq!(a, measure!(before));
        if case == "plain" || case == "hidden" {
            assert!(b.0 < a.0 && b.1 < a.1);
        }
        if case == "literal_lt" {
            assert_eq!(a, b);
        }
        println!("{case},4096,{},{},{},{}", a.0, b.0, a.1, b.1);
    }
}
