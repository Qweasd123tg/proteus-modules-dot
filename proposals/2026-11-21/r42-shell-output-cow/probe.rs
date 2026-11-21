// Side-by-side production render_result; fixture construction and result destruction
// are deliberately outside the measured region. No subprocess is started here.
use super::{SESSION_BUFFER_LIMIT, output as candidate, r42_before as stock};
use serde_json::{Value, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::time::{Duration, Instant};

thread_local! {
    static COUNTER: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}
struct Counting;
#[global_allocator]
static ALLOC: Counting = Counting;
fn charge(bytes: usize) {
    COUNTER.with(|c| {
        if let Some((n, b)) = c.get() {
            c.set(Some((n + 1, b + bytes)));
        }
    });
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        charge(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        charge(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, old: Layout, new: usize) -> *mut u8 {
        charge(new);
        unsafe { System.realloc(p, old, new) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
}

fn run(
    after: bool,
    data: &[u8],
    omitted: usize,
    status: Option<Option<i32>>,
    budget: usize,
    meta: &Value,
) -> (String, usize, usize, u128) {
    let bytes = data.to_vec();
    let metadata = meta.clone();
    let id = "test\0\"界";
    let wall = Duration::from_micros(15678);
    let exited = status.is_some();
    let exit_code = status.flatten();
    let start = Instant::now();
    COUNTER.with(|c| c.set(Some((0, 0))));
    let out = if after {
        candidate::render_result(
            id,
            71,
            candidate::Collected {
                bytes,
                dropped_bytes: omitted,
                exited,
                exit_code,
            },
            wall,
            budget,
            metadata,
        )
    } else {
        stock::render_result(
            id,
            71,
            stock::Collected {
                bytes,
                dropped_bytes: omitted,
                exited,
                exit_code,
            },
            wall,
            budget,
            metadata,
        )
    };
    let (n, b) = COUNTER.with(|c| c.replace(None).unwrap());
    let ns = start.elapsed().as_nanos();
    (out, n, b, ns)
}

#[test]
fn compare_renderers() {
    let small: &[&[u8]] = &[
        b"",
        b"a",
        b"\0\"\\\r\na",
        "abc".as_bytes(),
        "ж🙂界".as_bytes(),
        &[0xff, 0xf0, 0x80],
        &[0xed, 0xa0, 0x80, b'z'],
        &[0xe4, 0xb8],
        &[0xf0, 0x9f, 0x98, 0x80, 0xff],
    ];
    let metadata = [
        Value::Null,
        json!("preserved"),
        json!({"source_capture": null}),
        json!({"extra":["nested",42],"output_bytes":123,"source_capture":{"handle":"h\n🙂","storage_state":"sealed","complete_stream":true}}),
    ];
    let mut count = 0;
    for raw in small {
        for budget in 0..=20 {
            for meta in &metadata {
                for status in [None, Some(None), Some(Some(0)), Some(Some(17))] {
                    assert_eq!(
                        run(false, raw, 0, status, budget, meta).0,
                        run(true, raw, 0, status, budget, meta).0
                    );
                    count += 1;
                }
            }
        }
    }
    let mut big = vec![b'a'; SESSION_BUFFER_LIMIT];
    big[SESSION_BUFFER_LIMIT / 2 - 1] = 0xff;
    big[SESSION_BUFFER_LIMIT / 2] = 0x80;
    for omitted in [1, 73, 123456] {
        for budget in [
            0,
            1,
            2,
            13,
            40_000,
            SESSION_BUFFER_LIMIT,
            SESSION_BUFFER_LIMIT + 100,
        ] {
            assert_eq!(
                run(false, &big, omitted, Some(Some(0)), budget, &metadata[3]).0,
                run(true, &big, omitted, Some(Some(0)), budget, &metadata[3]).0
            );
            count += 1;
        }
    }
    println!("byte-identical complete wire replies: {count}");
    for (label, data, omitted, budget, meta) in [
        ("empty", vec![], 0, 40_000, json!({})),
        (
            "small",
            b"small command output\n".to_vec(),
            0,
            40_000,
            json!({}),
        ),
        ("fits_32k", vec![b'a'; 32_768], 0, 40_000, json!({})),
        ("ascii_1m_to_40k", vec![b'a'; 1 << 20], 0, 40_000, json!({})),
        (
            "unicode_1m_to_257",
            "🙂".repeat(1 << 18).into_bytes(),
            0,
            257,
            metadata[3].clone(),
        ),
        (
            "invalid_32k_to_257",
            vec![0xff; 32_768],
            0,
            257,
            metadata[3].clone(),
        ),
        (
            "dropped_middle",
            big.clone(),
            32_000,
            40_000,
            metadata[3].clone(),
        ),
        (
            "metadata_256k",
            b"short".to_vec(),
            0,
            40_000,
            json!({"attachment":"x".repeat(1<<18)}),
        ),
    ] {
        let mut ns = [Vec::new(), Vec::new()];
        let mut counts = [(0, 0); 2];
        for i in 0..45 {
            let mut result = Vec::new();
            for idx in [i % 2, (i + 1) % 2] {
                let (out, n, b, t) = run(idx == 1, &data, omitted, Some(Some(0)), budget, &meta);
                result.push(out);
                if i >= 4 {
                    ns[idx].push(t);
                    if i == 4 {
                        counts[idx] = (n, b);
                    }
                    assert_eq!(counts[idx], (n, b));
                }
            }
            assert_eq!(result[0], result[1]);
        }
        let median = |v: &mut Vec<u128>| {
            v.sort_unstable();
            v[v.len() / 2]
        };
        println!(
            "{label}: calls {} -> {}; requested bytes {} -> {}; median ns {} -> {}",
            counts[0].0,
            counts[1].0,
            counts[0].1,
            counts[1].1,
            median(&mut ns[0]),
            median(&mut ns[1])
        );
        if data.len() >= 32768 || label == "metadata_256k" {
            assert!(counts[1].1 < counts[0].1);
        }
    }
}
