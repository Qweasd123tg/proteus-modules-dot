#[path = "../after/value_hash.rs"]
mod after;
#[path = "../before/value_hash.rs"]
mod before;

use serde_json::{Value, json};
use std::hint::black_box;

#[repr(C)]
struct Timespec {
    sec: i64,
    nsec: i64,
}
unsafe extern "C" {
    fn clock_gettime(kind: i32, t: *mut Timespec) -> i32;
}
fn thread_ns() -> u128 {
    let mut t = Timespec { sec: 0, nsec: 0 };
    assert_eq!(unsafe { clock_gettime(3, &mut t) }, 0);
    (t.sec as u128) * 1_000_000_000 + (t.nsec as u128)
}

fn object_approx_max(n: usize, prefix_len: usize, late_inversion: bool) -> Value {
    let prefix = "x".repeat(prefix_len);
    let mut order = (0..n).collect::<Vec<_>>();
    if late_inversion {
        order.swap(n - 2, n - 1);
    }
    Value::Object(
        order
            .into_iter()
            .map(|i| (format!("{prefix}{i:05}"), json!(i)))
            .collect(),
    )
}

type Hash = fn(&Value) -> anyhow::Result<String>;
#[inline(never)]
fn run(h: Hash, val: &Value, iters: usize) -> u128 {
    let t = thread_ns();
    for _ in 0..iters {
        black_box(h(black_box(val)).unwrap());
    }
    thread_ns() - t
}

fn main() {
    let page = Value::Array(
        (0..50)
            .map(|i| json!({"args":{"max":i,"min":i},"id":i,"text":format!("row {i}")}))
            .collect(),
    );
    let reverse_page = Value::Array(
        (0..50)
            .map(|i| json!({"text":format!("row {i}"),"id":i,"args":{"min":i,"max":i}}))
            .collect(),
    );
    for (name, node, iters) in [
        ("cache-page-sorted", page, 1400),
        ("cache-page-reverse", reverse_page, 1400),
        (
            "32-128-bounded-late-inversion",
            object_approx_max(32, 123, true),
            2000,
        ),
        (
            "33-128-skipped-late-inversion",
            object_approx_max(33, 123, true),
            2000,
        ),
        (
            "4096-128-skipped-late-inversion",
            object_approx_max(4096, 123, true),
            30,
        ),
        (
            "4096-260-skipped-late-inversion",
            object_approx_max(4096, 255, true),
            24,
        ),
    ] {
        let keys: Vec<_> = node
            .as_object()
            .map(|m| m.keys().collect())
            .unwrap_or_default();
        let comparisons = if keys.len() <= 32 {
            let mut n = 0;
            if keys.first().is_none_or(|k| k.len() <= 128) {
                for pair in keys.windows(2) {
                    if pair[1].len() > 128 {
                        break;
                    }
                    n += 1;
                    if pair[0] >= pair[1] {
                        break;
                    }
                }
            }
            Some(n)
        } else {
            Some(0)
        };
        let f = before::storage_value_etag;
        let g = after::storage_value_etag;
        assert_eq!(f(&node).unwrap(), g(&node).unwrap());
        run(f, &node, iters);
        run(g, &node, iters);
        let mut a = Vec::new();
        let mut b = Vec::new();
        for i in 0..12 {
            if i % 2 == 0 {
                b.push(run(f, &node, iters));
                a.push(run(g, &node, iters));
            } else {
                a.push(run(g, &node, iters));
                b.push(run(f, &node, iters));
            }
        }
        println!(
            "{}",
            json!({"shape":name,"iterations":iters,"before_cpu_ns":b,"after_cpu_ns":a,
            "extra_adjacent_key_comparisons_per_top_level_object":if keys.is_empty(){None}else{comparisons},
            "preserve_order":cfg!(feature="preserve_order")})
        );
    }
}
