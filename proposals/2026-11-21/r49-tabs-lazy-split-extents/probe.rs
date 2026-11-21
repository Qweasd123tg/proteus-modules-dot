use proteus_tabs::{Node, Size, TabLayout};
use serde_json::{Value, json};
use std::hint::black_box;

#[cfg(feature = "count")]
mod alloc {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
    struct Meter;
    static CALLS: AtomicU64 = AtomicU64::new(0);
    static BYTES: AtomicU64 = AtomicU64::new(0);
    #[global_allocator]
    static ALLOC: Meter = Meter;
    unsafe impl GlobalAlloc for Meter {
        unsafe fn alloc(&self, l: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(l.size() as u64, Relaxed);
            unsafe { System.alloc(l) }
        }
        unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(n as u64, Relaxed);
            unsafe { System.realloc(p, l, n) }
        }
        unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
            unsafe { System.dealloc(p, l) }
        }
    }
    pub fn read() -> (u64, u64) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}

fn make(shape: &[usize], seed: u32) -> TabLayout {
    fn node(shape: &[usize], seed: u32, col: bool, next: &mut u32) -> Value {
        if let Some((&count, rest)) = shape.split_first() {
            let children: Vec<_> = (0..count)
                .map(|n| {
                    let k = (seed + n as u32 * 7 + *next) % 23;
                    // A split always retains at least one weighted child.
                    let size = if n == 0 || k % 3 != 0 {
                        json!({"weight":(1.+k as f32)/3.})
                    } else {
                        json!({"fixed":101.125 + k as f32 * 24.})
                    };
                    json!({"size":size, "node":node(rest,seed+13,!col,next)})
                })
                .collect();
            json!({"split":{"axis":if col {"column"} else {"row"}, "children":children}})
        } else {
            let id = *next;
            *next += 1;
            let tab = format!("files:tab{id}");
            json!({"pane":{"id":id,"tabs":[tab],"pinned":0,"active":tab}})
        }
    }
    let mut next = 0;
    let root = node(shape, seed, seed % 2 != 0, &mut next);
    let layout: TabLayout =
        serde_json::from_value(json!({"root":root,"focused":0,"next_id":next})).unwrap();
    layout.validate().unwrap();
    layout
}

fn dump() {
    let dims = [
        (1600., 900., 1.),
        (901.375, 511.0625, 2.75),
        (201., 19., 5.),
        (1., 1., 3.),
        (0., -0., 0.),
        (-10., -1., 1.),
        (0., 5., -3.),
        (f32::MIN_POSITIVE, f32::MAX, 0.75),
        (f32::INFINITY, 42., 1.),
        (17., f32::NEG_INFINITY, 0.),
        (f32::NAN, 11., 1.),
        (3., 13., f32::NAN),
    ];
    let mut layouts = Vec::new();
    for seed in 0..16 {
        for shape in [
            &[][..],
            &[2],
            &[3],
            &[13],
            &[2, 3],
            &[3, 2, 2],
            &[2, 2, 2, 2],
            &[3, 3, 3, 3],
        ] {
            layouts.push(make(shape, seed));
        }
    }
    // Adversarial in-memory inputs, not persisted valid layouts; compare the
    // original unchecked read-only geometry contract without admitting them.
    for size in [
        Size::Fixed(-0.),
        Size::Fixed(-2.),
        Size::Fixed(f32::INFINITY),
        Size::Fixed(f32::NAN),
        Size::Weight(-1.),
        Size::Weight(0.),
        Size::Weight(f32::NAN),
        Size::Weight(f32::INFINITY),
    ] {
        let mut layout = make(&[3, 2], 0);
        if let Node::Split(split) = &mut layout.root {
            for child in &mut split.children {
                child.size = size;
            }
        }
        layouts.push(layout);
    }
    for (i, layout) in layouts.iter().enumerate() {
        for (j, &(w, h, g)) in dims.iter().enumerate() {
            print!("{i}/{j}");
            for (id, r) in layout.rects_spaced(w, h, g) {
                print!(
                    " {}:{:08x},{:08x},{:08x},{:08x}",
                    id.0,
                    r.x.to_bits(),
                    r.y.to_bits(),
                    r.w.to_bits(),
                    r.h.to_bits()
                );
            }
            println!();
        }
    }
}

fn graph(node: &Node) -> (usize, usize) {
    match node {
        Node::Pane(_) => (0, 0),
        Node::Split(s) => s.children.iter().fold((1, s.children.len()), |(n, e), c| {
            let (m, f) = graph(&c.node);
            (n + m, e + f)
        }),
    }
}

fn main() {
    let cmd = std::env::args().nth(1).unwrap();
    if cmd == "dump" {
        dump();
        return;
    }
    let cases: [(&str, &[usize], u32); 5] = [
        ("single", &[], 0),
        ("two-pane", &[2], 1),
        ("four-pane-grid", &[2, 2], 2),
        ("eight-wide", &[8], 4),
        ("64-pane-stress", &[2, 2, 2, 2, 2, 2], 5),
    ];
    for (name, shape, seed) in cases {
        let layout = make(shape, seed);
        let (splits, edges) = graph(&layout.root);
        let call = || layout.rects_spaced(black_box(1280.5), black_box(800.25), black_box(1.));
        drop(black_box(call()));
        #[cfg(feature = "count")]
        {
            let (s, b) = alloc::read();
            let out = black_box(call());
            let (t, d) = alloc::read();
            assert_eq!(out.len(), layout.next_id as usize);
            println!(
                "alloc\t{cmd}\t{name}\t{splits}\t{edges}\t{}\t{}",
                t - s,
                d - b
            );
        }
        #[cfg(not(feature = "count"))]
        {
            let n = 200_000 / (1 + splits / 4);
            for _ in 0..200 {
                drop(black_box(call()));
            }
            let start = std::time::Instant::now();
            for _ in 0..n {
                drop(black_box(call()));
            }
            let ns = start.elapsed().as_nanos() as f64 / n as f64;
            println!("time\t{cmd}\t{name}\t{ns:.3}");
            black_box(edges);
        }
    }
}
