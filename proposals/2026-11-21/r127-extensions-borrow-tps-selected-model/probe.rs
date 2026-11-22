// Test-only selected TPS identity counters, outside the product patch.
use super::*;

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

thread_local! {
    static METER: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

fn record(size: usize) {
    let _ = METER.try_with(|meter| {
        if let Some((calls, bytes)) = meter.get() {
            meter.set(Some((calls + 1, bytes + size)));
        }
    });
}

struct Allocations;

unsafe impl GlobalAlloc for Allocations {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            record(size);
        }
        ptr
    }
}

#[global_allocator]
static GLOBAL: Allocations = Allocations;

fn scope<T>(op: impl FnOnce() -> T) -> (T, usize, usize) {
    assert!(METER.replace(Some((0, 0))).is_none());
    let out = std::hint::black_box(op());
    let (calls, bytes) = METER.take().unwrap();
    (out, calls, bytes)
}

#[derive(Clone, Copy, Debug, Default)]
struct Counts {
    reads: usize,
    resets: usize,
    owned: usize,
    owned_bytes: usize,
}

thread_local! {
    static COUNTS: Cell<Option<Counts>> = const { Cell::new(None) };
}

fn update(f: impl FnOnce(&mut Counts)) -> bool {
    COUNTS.with(|c| {
        if let Some(mut old) = c.get() {
            f(&mut old);
            c.set(Some(old));
            true
        } else {
            false
        }
    })
}

pub(crate) fn read_key() {
    update(|c| c.reads += 1);
}

pub(crate) fn reset() {
    update(|c| c.resets += 1);
}

pub(crate) fn owned(text: &str) -> String {
    update(|c| {
        c.owned += 1;
        c.owned_bytes += text.len();
    });
    text.to_owned()
}

pub(crate) fn active() -> bool {
    COUNTS.with(|r| r.get().is_some())
}

fn configured(provider: Value, name: Value, extra: usize) -> Value {
    json!({"config":{"model":{"provider":provider,"name":name,"label":format!("ignored-{extra}"),
                             "nested":{"counter":extra}}},
           "execution":{"active":null},"activity":{"running_runs":0}})
}

fn key(provider: &str, name: &str) -> Model {
    Model {provider:provider.to_owned(), name:name.to_owned()}
}

#[test]
fn measure_tps_identity() {
    println!(); // keep first counter separate from libtest's status prefix
    const P1: &str = "fixture-provider";
    const N1: &str = "standard-model";
    const P2: &str = "провайдер-🧪-secondary";
    const N2: &str = "большая-модель-fixture-wide";
    const S1: &str = "/fixture-tps/session-a";
    const S2: &str = "/fixture-tps/session-b";
    let cases = [
        ("same-once", json!(P1), json!(N1), Some((P1,N1)), Some(S1), 1, false, Some((P1,N1))),
        ("same-dozen", json!(P1), json!(N1), Some((P1,N1)), Some(S1), 12, false, Some((P1,N1))),
        ("unicode-dozen", json!(P2), json!(N2), Some((P2,N2)), Some(S1), 12, false, Some((P2,N2))),
        ("partial-name", json!(P1), json!(42), None, Some(S1), 1, false, None),
        ("bad-provider", Value::Null, json!(N1), None, Some(S1), 1, false, None),
        ("empty-pair", json!(""), json!(""), Some(("","")), Some(S1), 1, false, Some(("",""))),
        ("provider-reset", json!(P2), json!(N1), Some((P1,N1)), Some(S1), 1, true, Some((P2,N1))),
        ("name-reset", json!(P1), json!(N2), Some((P1,N1)), Some(S1), 1, true, Some((P1,N2))),
        ("session-reset", json!(P1), json!(N1), Some((P1,N1)), Some(S2), 1, true, Some((P1,N1))),
        ("malformed-reset", json!(P1), Value::Null, Some((P1,N1)), Some(S1), 1, true, None),
        ("missing-session", json!(P1), json!(N1), Some((P1,N1)), None, 1, true, Some((P1,N1))),
    ];
    for (case, provider, name, old, session, repeats, reset_expected, selected) in cases {
        let deadline = Instant::now() + Duration::from_secs(60);
        let mut tps = Tps {
            session: Some(S1.to_owned()),
            model: old.map(|(p,n)|key(p,n)),
            sample: Some(Sample {model:key(P1,N1), output:120, elapsed_ms:2000}),
            error: Some("previous controlled error".to_owned()),
            loaded: true,
            stale: true,
            running: true,
            deadline: Some(deadline),
        };
        let mut host = Host::default();
        host.session = session.map(str::to_owned);
        let states: Vec<_> = (0..repeats).map(|i| configured(provider.clone(),name.clone(),i)).collect();
        assert!(COUNTS.replace(Some(Counts::default())).is_none());
        let ((), allocs, requested) = scope(|| {
            for (i,state) in states.into_iter().enumerate() {
                host.state = Some(state);
                let surface = if i % 2 == 0 { Surface::Badge } else { Surface::Popup };
                std::hint::black_box(tps.render(&mut host, "probe", surface, None)).unwrap();
            }
        });
        let counts = COUNTS.take().unwrap();
        assert_eq!(counts.reads,repeats);
        assert_eq!(counts.resets,usize::from(reset_expected));
        assert_eq!(tps.session.as_deref(),session);
        let retained = tps.model.as_ref().map(|m|(m.provider.as_str(),m.name.as_str()));
        assert_eq!(retained,selected);
        assert_eq!(tps.deadline, if reset_expected {None} else {Some(deadline)});
        assert_eq!((tps.loaded,tps.stale,tps.running,tps.sample.is_some(),tps.error.is_some()),
                   (!reset_expected,!reset_expected,!reset_expected,!reset_expected,!reset_expected));
        let p = provider.as_str().map(str::len).unwrap_or_default();
        let n = name.as_str().map(str::len).unwrap_or_default();
        println!("ops {case} {repeats} {p} {n} {} {} {} {} {allocs} {requested}",
                 counts.reads,counts.resets,counts.owned,counts.owned_bytes);
        println!("shape {case} {}",json!({"session":tps.session,"model":retained,
                 "kept_deadline":tps.deadline==Some(deadline),"sample":tps.sample.as_ref().map(|s|s.output),
                 "error":tps.error,"loaded":tps.loaded,"stale":tps.stale,"running":tps.running}));
    }
}
