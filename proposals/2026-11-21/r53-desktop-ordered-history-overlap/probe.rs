mod stock;
use desktop_window_overlap_probe::fixtures::{fresh_core_seek, older_codex_page, resumed_codex};
use desktop_window_overlap_probe::transcript::{Change, Entry, Role, window_changes};
use std::hint::black_box;
use std::sync::Arc;

#[cfg(feature = "count")]
mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static A: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(new, Relaxed);
            unsafe { System.realloc(p, layout, new) }
        }
    }
    pub fn read() -> (usize, usize) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}

fn rows(keys: impl IntoIterator<Item = u64>, label: &str) -> Vec<Entry> {
    let text: Arc<str> = label.into();
    keys.into_iter()
        .map(|key| Entry {
            key,
            message_id: None,
            role: Role::Assistant,
            text: text.clone(),
            images: Vec::new(),
            tool: None,
            subagent: None,
            streaming: false,
            time: None,
        })
        .collect()
}

fn check(old: &[Entry], new: &[Entry]) {
    assert_eq!(
        window_changes(old, new),
        stock::window_changes(old, new),
        "lengths {}/{}",
        old.len(),
        new.len()
    );
}

fn generated() -> [(
    &'static str,
    desktop_window_overlap_probe::transcript::Transcript,
    desktop_window_overlap_probe::transcript::Transcript,
    bool,
); 4] {
    let (a, b) = resumed_codex(65);
    let (c, d) = resumed_codex(200);
    let (e, f) = fresh_core_seek();
    let (g, h) = older_codex_page();
    [
        ("codex-resume-65", a, b, true),
        ("codex-resume-200", c, d, true),
        ("core-seek-50", e, f, true),
        ("codex-prepend-control", g, h, false),
    ]
}

fn parity() {
    let mut cases = 0;
    for a in [0, 1, 4, 15, 16, 20, 21, 22, 50, 200, 320] {
        let old = rows(0..a, "old");
        for b in [0, 1, 15, 16, 17, 50, 200, 320, 2048, 2049] {
            for start in [0, 1, 4, 15, 20, 21, 65, 199, 5000] {
                let new = rows(start..start + b, "different text for the same row key");
                check(&old, &new);
                cases += 1;
            }
        }
    }
    // A deterministic mix of duplicate keys, reordered/nonoverlapping rows
    // and repeated runs exercises the exact script, not just final length.
    let mut state = 1u64;
    let mut rand = || {
        state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        state >> 32
    };
    for ix in 0..3000 {
        let (a, b) = (rand() % 230, rand() % 230);
        let old = rows((0..a).map(|_| rand() % 97), "old");
        let mut new = rows((0..b).map(|_| 1000 + rand() % 97), "new");
        if ix % 3 != 0 && a > 0 && b > 0 {
            let key = old[(rand() % a) as usize].key;
            new[(rand() % b) as usize].key = key;
            new[(rand() % b) as usize].key = key;
        }
        check(&old, &new);
        cases += 1;
    }
    for (name, old, new, wanted) in generated() {
        let old = old.entries();
        let new = new.entries();
        let sorted = new.is_sorted_by_key(|row| row.key);
        assert_eq!(sorted, wanted, "{name}");
        check(old, new);
        println!(
            "FIXTURE {name}: old_rows={} old_key_edges={}..{} new_rows={} new_key_edges={}..{} new_ordered={sorted}",
            old.len(),
            old[0].key,
            old.last().unwrap().key,
            new.len(),
            new[0].key,
            new.last().unwrap().key
        );
        cases += 1;
    }
    println!("PASS {cases} exact full Change script comparisons");
}

fn measure(call: impl Fn() -> Vec<Change>, arm: &str, name: &str, _n: usize) {
    #[cfg(feature = "count")]
    {
        let (a, b) = counter::read();
        let result = black_box(call());
        let (c, d) = counter::read();
        black_box(&result);
        println!("alloc\t{arm}\t{name}\t{}\t{}", c - a, d - b);
    }
    #[cfg(not(feature = "count"))]
    {
        for _ in 0..40 {
            drop(black_box(call()));
        }
        let now = std::time::Instant::now();
        for _ in 0.._n {
            drop(black_box(call()));
        }
        let ns = now.elapsed().as_nanos() as f64 / _n as f64;
        println!("time\t{arm}\t{name}\t{ns:.3}");
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
        return;
    }
    let old = rows(0..200, "old");
    for (name, start, count, iter) in [
        ("same-200", 0, 200, 30000),
        ("shift-4", 4, 200, 20000),
        ("shift-24", 24, 200, 9000),
        ("shift-65", 65, 200, 4000),
        ("disjoint-50", 500, 50, 4000),
        ("disjoint-200", 500, 200, 2000),
        ("shuffled-disjoint", 500, 200, 2000),
    ] {
        let mut new = rows(start..start + count, "new");
        if name == "shuffled-disjoint" {
            new.reverse();
        }
        check(&old, &new);
        let chosen = match arm.as_str() {
            "stock" => stock::window_changes,
            "candidate" => window_changes,
            _ => panic!("expected parity, stock or candidate"),
        };
        let call = || chosen(black_box(&old), black_box(&new));
        measure(call, &arm, name, iter);
    }
    for (name, old, new, _) in generated() {
        let old = old.entries();
        let new = new.entries();
        let chosen = match arm.as_str() {
            "stock" => stock::window_changes,
            "candidate" => window_changes,
            _ => unreachable!(),
        };
        measure(|| chosen(black_box(old), black_box(new)), &arm, name, 1000);
    }
}
