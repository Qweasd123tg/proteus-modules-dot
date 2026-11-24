#[path = "../after/value_hash.rs"]
mod after;
#[path = "../before/value_hash.rs"]
mod before;
use serde_json::{Value, json};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    hint::black_box,
    sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed},
};

struct Meter;
#[global_allocator]
static A: Meter = Meter;
static ACTIVE: AtomicBool = AtomicBool::new(false);
static A_COUNT: AtomicU64 = AtomicU64::new(0);
static R_COUNT: AtomicU64 = AtomicU64::new(0);
static BYTES: AtomicU64 = AtomicU64::new(0);
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        if ACTIVE.load(Relaxed) {
            A_COUNT.fetch_add(1, Relaxed);
            BYTES.fetch_add(l.size() as u64, Relaxed);
        }
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        if ACTIVE.load(Relaxed) {
            A_COUNT.fetch_add(1, Relaxed);
            BYTES.fetch_add(l.size() as u64, Relaxed);
        }
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        if ACTIVE.load(Relaxed) {
            R_COUNT.fetch_add(1, Relaxed);
            BYTES.fetch_add(n as u64, Relaxed);
        }
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
fn measure(f: fn(&Value) -> anyhow::Result<String>, v: &Value) -> (String, [u64; 3]) {
    for a in [&A_COUNT, &R_COUNT, &BYTES] {
        a.store(0, Relaxed);
    }
    ACTIVE.store(true, Relaxed);
    let output = black_box(f(black_box(v)).unwrap());
    ACTIVE.store(false, Relaxed);
    (
        output,
        [
            A_COUNT.load(Relaxed),
            R_COUNT.load(Relaxed),
            BYTES.load(Relaxed),
        ],
    )
}
fn oracle(v: &Value) -> String {
    let mut copy = v.clone();
    copy.sort_all_objects();
    let bytes = serde_json::to_vec(&copy).unwrap();
    ring::digest::digest(&ring::digest::SHA256, &bytes)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn object_counts(v: &Value) -> (u64, u64) {
    match v {
        Value::Object(m) => m.values().map(object_counts).fold(
            (
                u64::from(!m.is_empty()),
                u64::from(
                    !m.is_empty()
                        && m.len() <= 32
                        && m.keys().all(|k| k.len() <= 128)
                        && m.keys().is_sorted(),
                ),
            ),
            |(before, after), (a, b)| (before + a, after + b),
        ),
        Value::Array(xs) => xs
            .iter()
            .map(object_counts)
            .fold((0, 0), |(x, y), (a, b)| (x + a, y + b)),
        _ => (0, 0),
    }
}
fn make_object(order: &[&str]) -> Value {
    Value::Object(
        order
            .iter()
            .map(|s| (s.to_string(), json!({"a":"NUL\u{0}\n","b":-0.0})))
            .collect(),
    )
}

fn ordered_object(n: usize, prefix_bytes: usize, late_inversion: bool) -> Value {
    let prefix = "x".repeat(prefix_bytes);
    let mut indexes = (0..n).collect::<Vec<_>>();
    if late_inversion {
        indexes.swap(n - 2, n - 1);
    }
    Value::Object(
        indexes
            .into_iter()
            .map(|i| (format!("{prefix}{i:05}"), json!(i)))
            .collect(),
    )
}

fn main() {
    let a = make_object(&["a", "ba", "bb", "я", "🦀"]);
    let b = make_object(&["🦀", "я", "bb", "ba", "a"]);
    assert_eq!(oracle(&a), oracle(&b));
    let sorted = make_object(&["é", "я", "🚀"]);
    let unsorted = make_object(&["🚀", "я", "é"]);
    let mut vs = vec![
        ("null", Value::Null),
        ("bool", json!(true)),
        ("empty-object", json!({})),
        ("empty-array", json!([])),
        ("known", json!({"z":2,"a":[1,true]})),
        ("one-key", json!({"z":2})),
        ("nested-sorted", a),
        ("nested-reversed", b),
        ("key-order-sorted", sorted.clone()),
        ("key-order-unsorted", unsorted.clone()),
        ("large-string", json!("x".repeat(1 << 20))),
        (
            "50-row-sorted",
            Value::Array(
                (0..50)
                    .map(|n| json!({"args":{"max":n,"min":n},"id":n,"text":format!("record {n}")}))
                    .collect(),
            ),
        ),
        (
            "50-row-unsorted",
            Value::Array(
                (0..50)
                    .map(|n| json!({"text":format!("record {n}"),"id":n,"args":{"min":n,"max":n}}))
                    .collect(),
            ),
        ),
        (
            "nested-mixed",
            json!({"a":[sorted,unsorted],"z":{"e":1,"d":2,"c":3,"b":4}}),
        ),
        ("32-near-limit-sorted", ordered_object(32, 123, false)),
        ("32-keys-late-inversion", ordered_object(32, 123, true)),
        ("33-keys-default-fallback", ordered_object(33, 123, false)),
        ("long-key-default-fallback", ordered_object(2, 124, false)),
        ("4096-keys-late-inversion", ordered_object(4096, 123, true)),
        (
            "4096-keys-long-late-inversion",
            ordered_object(4096, 255, true),
        ),
    ];
    for n in 0..4096 {
        let mut order = ["a", "b", "c", "d", "e"];
        order.rotate_left(n % 5);
        if n & 8 != 0 {
            order.reverse()
        };
        let mut node = make_object(&order);
        node.as_object_mut()
            .unwrap()
            .insert("nested".into(), json!([{"z":n,"a":n+1},null,{},[],{"x":n}]));
        vs.push(("generated", node));
    }
    let mut total = std::collections::BTreeMap::new();
    for (shape, v) in &vs {
        let expected = oracle(v);
        let (old, bc) = measure(before::storage_value_etag, v);
        let (new, ac) = measure(after::storage_value_etag, v);
        assert_eq!(old, expected);
        assert_eq!(new, expected);
        assert_eq!(new.len(), 64);
        let (nonempty, sorted) = object_counts(v);
        assert_eq!(bc[0] as i64 - ac[0] as i64, sorted as i64);
        assert_eq!(ac[0], nonempty - sorted + 1);
        assert_eq!(bc[1], ac[1]);
        assert_eq!(ac[1], 0);
        assert!(bc[2] >= ac[2]);
        let entry = total.entry(*shape).or_insert([0, 0, 0]);
        entry[0] += 1;
        entry[1] += bc[0] - ac[0];
        entry[2] += bc[2] - ac[2];
        if *shape == "known" {
            assert_eq!(
                new,
                "cab2365c93b4de12e8e2b0ec8b7a41a801a294b46c571adfdf87eed1d2342b2a"
            );
        }
        if *shape != "generated" {
            println!(
                "{}",
                json!({"shape":shape,"etag":new,"sorted_nonempty_objects":sorted,"nonempty_objects":nonempty,"before_alloc_realloc_grossreq":bc,"after_alloc_realloc_grossreq":ac})
            );
        }
    }
    println!(
        "{}",
        json!({"values":vs.len(),"totals_n_removed_alloc_removed_bytes":total,"preserve_order":cfg!(feature="preserve_order")})
    );
}
