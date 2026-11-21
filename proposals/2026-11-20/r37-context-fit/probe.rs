// Modules below must be the complete, unmodified budget.rs files from both trees.
#[path = "budget-after.rs"]
mod candidate;
#[path = "budget-before.rs"]
mod stock;

use proteus_contracts::domain::{ContextChunk, ContextRenderMode};
use serde_json::json;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    hint::black_box,
    time::Instant,
};

thread_local! {static ALLOCS: Cell<Option<(usize,usize)>> = const { Cell::new(None) };}
struct Counter;
#[global_allocator]
static ALLOCATOR: Counter = Counter;
fn record(size: usize) {
    ALLOCS.with(|c| {
        if let Some((calls, bytes)) = c.get() {
            c.set(Some((calls + 1, bytes + size)))
        }
    });
}
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        record(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        record(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, old: Layout, size: usize) -> *mut u8 {
        record(size);
        unsafe { System.realloc(p, old, size) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
type Select = fn(Vec<ContextChunk>, usize) -> anyhow::Result<Vec<ContextChunk>>;
fn make(i: usize, seed: usize, size: usize, is_rules: bool) -> ContextChunk {
    let mut chunk = ContextChunk::new(format!("source-{i}"), "x".repeat(size))
        .with_metadata(
            json!({"provider":if is_rules{"project_instructions"}else{"search"},
          "sequence":i}),
        )
        .with_path(format!("f{i}.rs").into());
    if i % 5 != 2 {
        chunk.score = Some((((i + 3) * (seed + 5)) % 7) as f32 / 7.0);
    }
    if is_rules {
        chunk = chunk.with_render_mode(ContextRenderMode::Verbatim)
    }
    chunk
}
fn normalize(got: anyhow::Result<Vec<ContextChunk>>) -> Result<Vec<ContextChunk>, String> {
    got.map_err(|e| e.to_string())
}
#[test]
fn differential() {
    let mut cases = 0;
    for seed in 0..64 {
        let chunks: Vec<_> = (0..(seed % 17))
            .map(|i| make(i, seed, (seed * 13 + i * 11) % 23, (i + seed) % 5 == 2))
            .collect();
        let total: usize = chunks.iter().map(|c| c.content.len()).sum();
        for limit in (0..=total + 1).chain([usize::MAX]) {
            assert_eq!(
                normalize(stock::apply_byte_budget(chunks.clone(), limit)),
                normalize(candidate::apply_byte_budget(chunks.clone(), limit)),
                "seed={seed},limit={limit}"
            );
            cases += 1;
        }
    }
    println!("identical outputs / exact error strings across {cases} cases");
}
fn measure(method: Select, input: &[ContextChunk], limit: usize) -> (u128, (usize, usize)) {
    let input = input.to_vec();
    ALLOCS.set(Some((0, 0)));
    let start = Instant::now();
    let got = black_box(method(black_box(input), black_box(limit)).unwrap());
    let nanos = start.elapsed().as_nanos();
    let counts = ALLOCS.replace(None).unwrap();
    drop(got);
    (nanos, counts)
}
#[test]
fn budget_cost() {
    println!("n,limit,old_ns,new_ns,old_calls,new_calls,old_req_bytes,new_req_bytes");
    for n in [8, 32, 128] {
        let size = 256;
        let input: Vec<_> = (0..n).map(|i| make(i, 3, size, i % 11 == 0)).collect();
        for limit in [n * size, n * size - 1, n * size / 2] {
            assert_eq!(
                stock::apply_byte_budget(input.clone(), limit).unwrap(),
                candidate::apply_byte_budget(input.clone(), limit).unwrap()
            );
            let mut a = vec![];
            let mut b = vec![];
            let mut counts = None;
            for j in 0..105 {
                let (old, new) = if j % 2 == 0 {
                    (
                        measure(stock::apply_byte_budget, &input, limit),
                        measure(candidate::apply_byte_budget, &input, limit),
                    )
                } else {
                    let new = measure(candidate::apply_byte_budget, &input, limit);
                    (measure(stock::apply_byte_budget, &input, limit), new)
                };
                if j >= 4 {
                    if let Some(counts) = counts {
                        assert_eq!(counts, (old.1, new.1));
                    }
                    counts = Some((old.1, new.1));
                    a.push(old.0);
                    b.push(new.0);
                }
            }
            a.sort_unstable();
            b.sort_unstable();
            let (old, new) = counts.unwrap();
            println!(
                "{n},{limit},{},{},{},{},{},{}",
                a[50], b[50], old.0, new.0, old.1, new.1
            );
        }
    }
}

#[test]
fn wire_scores() {
    // Use the same deserializer as retrieval::provider_chunks, including f32 narrowing.
    fn decode(raw: &str) -> serde_json::Result<Vec<ContextChunk>> {
        let bytes = format!(
            r#"[{{"source":"p","path":null,"content":"xx","render_mode":"verbatim","score":{raw},"metadata":null}}]"#
        );
        serde_json::from_str(&bytes)
    }
    for invalid in ["NaN", "\"NaN\"", "Infinity", "-Infinity", "1e100", "-1e100"] {
        assert!(
            decode(invalid).is_err(),
            "unexpected acceptance of {invalid}"
        );
    }
    let mut sample = Vec::new();
    for score in ["null", "3.0", "3e38", "-3e38", "-0.0", "0.0", "3.0"] {
        let chunk = decode(score).unwrap().pop().unwrap();
        println!("wire {score} parsed as {:?}", chunk.score);
        assert!(!chunk.score.is_some_and(|n| n.is_nan()));
        sample.push(chunk);
    }
    for limit in 0..=20 {
        assert_eq!(
            normalize(stock::apply_byte_budget(sample.clone(), limit)),
            normalize(candidate::apply_byte_budget(sample.clone(), limit))
        );
    }
}
