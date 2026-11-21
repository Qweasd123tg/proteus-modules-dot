// Optional later diagnostic module, separate from production source and normal wire runs.
use super::*;
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

thread_local! {
    static ACTIVE: Cell<bool> = const { Cell::new(false) };
    static COUNTS: Cell<(usize, usize)> = const { Cell::new((0, 0)) };
}

struct Meter;

#[global_allocator]
static METER: Meter = Meter;

fn record(bytes: usize) {
    if ACTIVE.try_with(Cell::get).unwrap_or(false) {
        COUNTS.with(|c| {
            let (calls, old_bytes) = c.get();
            c.set((calls + 1, old_bytes + bytes));
        });
    }
}

unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, previous: Layout, bytes: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, previous, bytes) };
        if !ptr.is_null() {
            record(bytes);
        }
        ptr
    }
}

fn measure<T>(f: impl FnOnce() -> T) -> (T, usize, usize) {
    COUNTS.with(|c| c.set((0, 0)));
    ACTIVE.with(|a| a.set(true));
    let out = std::hint::black_box(f());
    ACTIVE.with(|a| a.set(false));
    let (calls, bytes) = COUNTS.with(Cell::get);
    (out, calls, bytes)
}

#[derive(Default)]
struct Silent;

impl Extension for Silent {
    fn render(&mut self, _: &mut Host, _: &str, _: Surface, _: Option<&str>) -> Result {
        Ok(())
    }
}

#[test]
fn meter_session_membership_pruning() {
    println!();
    let many: Vec<_> = (0..128)
        .map(|i| format!("/synthetic/session/особый-{i:02}"))
        .collect();
    let unique: Vec<_> = many.iter().map(|id| Some(id.as_str())).collect();
    let single = [unique[0]];
    let shared = [unique[0]; 8];
    let eight = &unique[..8];
    for (case, routes, parked, active_instances) in [
        ("empty", &[None][..0], &[None][..0], &[None][..0]),
        ("one", &single[..], &[][..], &single[..]),
        ("shared-eight", &shared[..], &[][..], &single[..]),
        ("eight-live", eight, &eight[1..], eight),
        ("many-live", &unique[..], &unique[1..], &unique[..]),
    ] {
        let (mut host, mut ext) = (Host::default(), instances::Instances::new(Silent));
        host.contexts = routes
            .iter()
            .enumerate()
            .map(|(i, session)| {
                (
                    i.to_string(),
                    Scope {
                        session: session.map(str::to_owned),
                        ..Scope::default()
                    },
                )
            })
            .collect();
        for session in active_instances {
            host.session = session.map(str::to_owned);
            ext.render(&mut host, "test", Surface::Badge, None).unwrap();
        }
        for session in parked {
            host.sessions
                .insert(session.map(str::to_owned), SessionContext::default());
        }
        host.session = routes.first().copied().flatten().map(str::to_owned);
        host.current_context = (!routes.is_empty()).then(|| "0".to_owned());
        let repeat = 1000;
        let ((), calls, bytes) = measure(|| {
            for _ in 0..repeat {
                std::hint::black_box(&mut host).prune_sessions();
                std::hint::black_box(&mut ext).prune(&host);
            }
        });
        assert_eq!(host.sessions.len(), parked.len());
        assert_eq!(ext.count(), active_instances.len());
        assert_eq!(host.session.as_deref(), routes.first().copied().flatten());
        assert!(host.sent.borrow().is_empty());
        println!(
            "prune {case} {repeat} {} {} {} {calls} {bytes}",
            routes.len(),
            parked.len(),
            active_instances.len(),
        );
    }
}

fn dispatch(host: &mut Host, ext: &mut instances::Instances<Silent>, message: Value) {
    host.handle(ext, message).unwrap();
    ext.prune(host);
}

#[test]
fn duplicate_contexts_keep_parked_error_pending_and_state_until_last_route() {
    const A: &str = "/fixture/one";
    const B: &str = "/fixture/two";
    let (mut host, mut ext) = (Host::default(), instances::Instances::new(Silent));
    host.features.insert("session.settings.v1".into());
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"session_snapshot","context":"a",
        "session_dir":A,"state":{"config":{"profile":"first profile"}}}),
    );
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"render","context":"a","view":"a-view","surface":"badge","session_dir":A}),
    );
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"context","context":"duplicate","session_dir":A}),
    );
    host.set_session("mode", json!("plan")).unwrap();
    host.command_error = Some("fixture carried error".into());
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"session_snapshot","context":"b",
        "session_dir":B,"state":{"config":{"profile":"other profile"}}}),
    );
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"render","context":"b","view":"b-view","surface":"badge","session_dir":B}),
    );
    assert_eq!(ext.count(), 2);

    dispatch(&mut host, &mut ext, json!({"type":"close","view":"a-view"}));
    host.activate_context("b");
    let parked = Some(A.to_owned());
    assert_eq!(host.sessions.get(&parked).unwrap().pending().len(), 1);
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"close_context","context":"a"}),
    );
    assert_eq!(ext.count(), 2); // A duplicate with no view still retains the session.
    assert_eq!(
        host.sessions.get(&parked).unwrap().pending()[0].0,
        "setting-1"
    );
    host.activate_context("duplicate");
    assert_eq!(host.command_error.as_deref(), Some("fixture carried error"));
    assert_eq!(host.pending.len(), 1);
    assert_eq!(
        host.state.as_ref().unwrap()["config"]["profile"],
        "first profile"
    );

    host.activate_context("b");
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"close_context","context":"duplicate"}),
    );
    assert_eq!(ext.count(), 1);
    assert!(!host.sessions.contains_key(&parked));
    assert_eq!(
        host.state.as_ref().unwrap()["config"]["profile"],
        "other profile"
    );
    assert!(host.pending.is_empty());
    assert!(host.command_error.is_none());
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"context","context":"reopened","session_dir":A}),
    );
    assert!(host.state.is_none());
    assert!(host.pending.is_empty());
    assert!(host.command_error.is_none());
    assert!(host.awaiting_snapshot);
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"close_context","context":"reopened"}),
    );
    dispatch(&mut host, &mut ext, json!({"type":"close","view":"b-view"}));
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"close_context","context":"b"}),
    );
    assert!(host.current_context.is_none() && host.session.is_none());
    assert!(host.state.is_none() && host.pending.is_empty() && host.command_error.is_none());
    assert!(host.sessions.is_empty());
    assert_eq!(ext.count(), 0);
    println!("scope-parked duplicate-first-kept last-dropped fresh-on-reopen");
}

#[test]
fn empty_string_session_never_aliases_the_unassigned_route() {
    let (mut host, mut ext) = (Host::default(), instances::Instances::new(Silent));
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"session_snapshot","context":"unassigned",
        "session_dir":null,"state":{"marker":"none"}}),
    );
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"render","context":"unassigned",
        "view":"none-view","surface":"badge","session_dir":null}),
    );
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"session_snapshot","context":"empty",
        "session_dir":"","state":{"marker":"empty"}}),
    );
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"render","context":"empty",
        "view":"empty-view","surface":"badge","session_dir":""}),
    );
    assert_eq!(ext.count(), 2);
    assert_eq!(host.session.as_deref(), Some(""));
    assert!(host.sessions.contains_key(&None));
    host.activate_context("unassigned");
    assert_eq!(host.state.as_ref().unwrap()["marker"], "none");
    assert!(host.sessions.contains_key(&Some(String::new())));
    host.activate_context("empty");
    assert_eq!(host.state.as_ref().unwrap()["marker"], "empty");
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"close","view":"none-view"}),
    );
    host.activate_context("empty");
    dispatch(
        &mut host,
        &mut ext,
        json!({"type":"close_context","context":"unassigned"}),
    );
    assert_eq!(ext.count(), 1);
    assert!(!host.sessions.contains_key(&None));
    assert_eq!(host.session.as_deref(), Some(""));
    println!("scope-keys none-and-empty-isolated");
}
