use crate::tabs;
use proteus_contracts::contracts::ToolTerminalRef;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::cell::{Cell, OnceCell};
use std::collections::HashMap;
use std::hint::black_box;
use std::mem::size_of;
use std::path::PathBuf;
use std::rc::{Rc, Weak};
use tabs::TabLayout;

struct App;
type EntityId = usize;
#[derive(Clone, Copy)]
struct Api(u64);
impl Api {
    fn connection_id(&self) -> u64 {
        self.0
    }
}
struct SurfaceView {
    view: View,
}
struct View(EntityId);
impl View {
    fn entity_id(&self) -> EntityId {
        self.0
    }
}
type Documents = HashMap<String, SurfaceView>;
struct Parked {
    documents: Documents,
}
struct Workspace {
    api: Option<Api>,
    settings: Option<()>,
    layout: TabLayout,
    documents: Documents,
    parked_spaces: HashMap<usize, Parked>,
}
impl Workspace {
    fn api(&self) -> Option<&Api> {
        self.api.as_ref()
    }
}
struct WeakHandle(Weak<Workspace>);
impl WeakHandle {
    fn upgrade(&self) -> Option<ReadHandle> {
        self.0.upgrade().map(ReadHandle)
    }
    fn new(w: &Rc<Workspace>) -> Self {
        Self(Rc::downgrade(w))
    }
}
struct ReadHandle(Rc<Workspace>);
impl ReadHandle {
    fn read(&self, _: &App) -> &Workspace {
        self.0.as_ref()
    }
}
include!("workspace.inc.rs");

thread_local! { static ID_CALLS:Cell<usize>=const { Cell::new(0) }; }
fn note_id() {
    ID_CALLS.with(|c| c.set(c.get() + 1));
}
fn id_calls() -> usize {
    ID_CALLS.with(|c| c.replace(0))
}

mod guard {
    include!("guard.rs");
}
mod observed {
    include!("observed.rs");
}

const CANONICAL: &str = r#"agent-terminal:{"owner":"chat:/fixture/рабочая","session_dir":"/fixture/session 東京/é","terminal":{"id":"12345678-1234-4234-8234-123456789abc","title":"résumé\t😀 \"stdout\"","tty":true}}"#;
const ALIAS: &str = r#"agent-terminal: { "terminal":{"tty":true,"title":"r\u00e9sumé\t😀 \"stdout\"","id":"12345678-1234-4234-8234-123456789abc"},"session_dir":"/fixture/session 東京/é","owner":"chat:/fixture/рабочая" }"#;
const ENTITY: EntityId = 7;
fn doc(id: &str, entity: EntityId) -> Documents {
    HashMap::from([(id.into(), SurfaceView { view: View(entity) })])
}
fn model(
    key: &str,
    entity: EntityId,
    connected: Option<u64>,
    visible: bool,
    settings: bool,
    parked: bool,
) -> Rc<Workspace> {
    let mut layout = TabLayout::default();
    layout.open(if visible { key } else { "files:covered" }, |_| false);
    let (documents, parked_spaces) = if parked {
        (
            HashMap::new(),
            HashMap::from([(
                1,
                Parked {
                    documents: doc(key, entity),
                },
            )]),
        )
    } else {
        (doc(key, entity), HashMap::new())
    };
    Rc::new(Workspace {
        api: connected.map(Api),
        settings: settings.then_some(()),
        layout,
        documents,
        parked_spaces,
    })
}
fn target() -> guard::Target {
    guard::Target::parse(CANONICAL).unwrap()
}
fn guarded(remote: &guard::Remote, entity: EntityId) -> [bool; 2] {
    [remote.check_current(entity), remote.check_visible(entity)]
}

#[test]
fn parser_canonical_bytes_and_raw_alias_key_miss() {
    eprintln!("ARM {}", env!("R119_ARM"));
    let t = target();
    assert_eq!(t, guard::Target::parse(ALIAS).unwrap());
    assert_eq!(guard::original_id(&t), CANONICAL);
    let wrong = [
        CANONICAL.replacen("agent-terminal:", "other:", 1),
        CANONICAL.replacen("/fixture/session", "relative/session", 1),
        CANONICAL.replacen("chat:/fixture/рабочая", "files:wrong", 1),
        CANONICAL.replacen("\"tty\":true", "\"tty\":true,\"extra\":1", 1),
        CANONICAL.replacen("\"terminal\":", "\"extra\":1,\"terminal\":", 1),
        CANONICAL.replacen("12345678-1234-4234-8234-123456789abc", "not-a-uuid", 1),
        "agent-terminal:{".into(),
    ];
    assert!(wrong.iter().all(|s| guard::Target::parse(s).is_none()));
    let alias = model(ALIAS, ENTITY, Some(1), true, false, false);
    let canonical = model(CANONICAL, ENTITY, Some(1), true, false, false);
    let mut r = guard::Remote::new(
        guard::Target::parse(ALIAS).unwrap(),
        Api(1),
        WeakHandle::new(&alias),
    );
    let raw_miss = guarded(&r, ENTITY);
    assert_eq!(raw_miss, [false, false]);
    r.rehost(WeakHandle::new(&canonical));
    let canonical_hit = guarded(&r, ENTITY);
    assert_eq!(canonical_hit, [true, true]);
    let another = CANONICAL.replace(
        "12345678-1234-4234-8234-123456789abc",
        "87654321-1234-4234-8234-123456789abc",
    );
    let distinct = model(&another, ENTITY, Some(1), true, false, false);
    let r2 = guard::Remote::new(
        guard::Target::parse(&another).unwrap(),
        Api(1),
        WeakHandle::new(&distinct),
    );
    assert_eq!(guarded(&r2, ENTITY), [true, true]);
    assert_eq!(
        guard::original_id(&guard::Target::parse(&another).unwrap()),
        another
    );
    eprintln!(
        "TRACE canonical-alias {}",
        json!({"id":CANONICAL,"alias":ALIAS,"other":another,
         "alias_parses":true,"bad_rejected":wrong.len(),"raw_miss":raw_miss,"canonical_hit":canonical_hit})
    );
}

#[test]
fn retained_parked_entity_settings_rehost_and_connection_guards() {
    let original = model(CANONICAL, ENTITY, Some(1), true, false, false);
    let mut r = guard::Remote::new(target(), Api(1), WeakHandle::new(&original));
    assert_eq!(guarded(&r, ENTITY), [true, true]);
    let mut trace = vec![("active", [true, true])];
    for (label, entity, conn, visible, settings, parked, result) in [
        (
            "hidden",
            ENTITY,
            Some(1),
            false,
            false,
            false,
            [true, false],
        ),
        (
            "settings",
            ENTITY,
            Some(1),
            true,
            true,
            false,
            [true, false],
        ),
        ("parked", ENTITY, Some(1), true, false, true, [true, false]),
        (
            "changed-entity",
            ENTITY + 1,
            Some(1),
            true,
            false,
            false,
            [false, false],
        ),
        (
            "changed-connection",
            ENTITY,
            Some(8),
            true,
            false,
            false,
            [false, false],
        ),
        (
            "no-connection",
            ENTITY,
            None,
            true,
            false,
            false,
            [false, false],
        ),
        (
            "back-on-original-key",
            ENTITY,
            Some(1),
            true,
            false,
            false,
            [true, true],
        ),
    ] {
        let state = model(CANONICAL, entity, conn, visible, settings, parked);
        r.rehost(WeakHandle::new(&state));
        let got = guarded(&r, ENTITY);
        assert_eq!(got, result, "{label}");
        trace.push((label, got));
        if label == "changed-entity" {
            assert_eq!(guarded(&r, ENTITY + 1), [true, true]);
        }
    }
    assert_eq!(guarded(&r, ENTITY), [false, false]); // rehost's Weak owner dropped
    trace.push(("dropped", [false, false]));
    eprintln!("TRACE current-visible {}", json!(trace));
}

#[test]
fn lazy_encoder_count_preserves_order_and_one_key_per_used_viewer() {
    let stale = model(CANONICAL, ENTITY, Some(2), true, false, false);
    let connected = model(CANONICAL, ENTITY, Some(1), true, false, false);
    let mut r = observed::Remote::new(
        observed::Target::parse(CANONICAL).unwrap(),
        Api(1),
        WeakHandle::new(&stale),
    );
    let (_, calls, bytes) =
        crate::measurement(|| (r.check_current(ENTITY), r.check_visible(ENTITY)));
    assert_eq!((calls, bytes, id_calls()), (0, 0, 0));
    assert!(r.memo().is_none());
    r.rehost(WeakHandle::new(&connected));
    assert!(r.check_visible(ENTITY)); // first contact through the other guard
    assert_eq!(id_calls(), 1);
    for _ in 0..32 {
        assert!(r.check_current(ENTITY));
        assert!(r.check_visible(ENTITY));
    }
    let reuse = r.memo().is_some();
    let post = id_calls();
    assert_eq!(post, if reuse { 0 } else { 64 });
    let r2 = observed::Remote::new(
        observed::Target::parse(CANONICAL).unwrap(),
        Api(1),
        WeakHandle::new(&connected),
    );
    assert!(r2.check_current(ENTITY));
    assert_eq!(id_calls(), 1);
    if let (Some(a), Some(b)) = (r.memo(), r2.memo()) {
        assert_eq!(a, b);
        assert_ne!(a.as_ptr(), b.as_ptr());
    }
    let settings = model(CANONICAL, ENTITY, Some(1), true, true, false);
    let hidden = observed::Remote::new(
        observed::Target::parse(CANONICAL).unwrap(),
        Api(1),
        WeakHandle::new(&settings),
    );
    assert!(!hidden.check_visible(ENTITY));
    assert_eq!(id_calls(), 1); // same connection even though covered
    if reuse {
        assert_eq!(hidden.memo().map(String::as_str), Some(CANONICAL));
    }
    let nothing = model(CANONICAL, ENTITY, None, true, false, false);
    let mut missing = observed::Remote::new(
        observed::Target::parse(CANONICAL).unwrap(),
        Api(1),
        WeakHandle::new(&nothing),
    );
    assert!(!missing.check_visible(ENTITY));
    assert_eq!(id_calls(), 0);
    missing.rehost(WeakHandle(Weak::new()));
    assert!(!missing.check_current(ENTITY));
    assert_eq!(id_calls(), 0);
    assert!(missing.memo().is_none());
    eprintln!("WORK formatter {}", json!([0, 1, post, 1, 1, 0, 0]));
    eprintln!(
        "TRACE lazy-guards {}",
        json!({"failed_guard_skips":true,"first_visible":true,
         "later_current":true,"viewer_local":true})
    );
}

#[test]
fn allocated_work_cold_and_ordinary_warm_guard_ticks() {
    let state = model(CANONICAL, ENTITY, Some(1), true, false, false);
    let r = guard::Remote::new(target(), Api(1), WeakHandle::new(&state));
    let ((first_cur, first_vis), cold_calls, cold_bytes) =
        crate::measurement(|| (r.check_current(ENTITY), r.check_visible(ENTITY)));
    assert!(first_cur && first_vis);
    eprintln!("WORK cold {}", json!([2, cold_calls, cold_bytes]));
    let (n, calls, bytes) = crate::measurement(|| {
        let mut n = 0;
        for _ in 0..256 {
            n += usize::from(black_box(&r).check_visible(ENTITY));
            n += usize::from(black_box(&r).check_current(ENTITY));
        }
        n
    });
    assert_eq!(n, 512);
    eprintln!("WORK warm {}", json!([n, calls, bytes]));
    let (n, calls, bytes) = crate::measurement(|| {
        (0..256)
            .filter(|_| black_box(&r).check_current(ENTITY))
            .count()
    });
    assert_eq!(n, 256);
    eprintln!("WORK warm-current {}", json!([n, calls, bytes]));
    let (owned, capacity) = r.memo().map_or((0, 0), |s| (s.len(), s.capacity()));
    if let Some(key) = r.memo() {
        assert_eq!(key.as_bytes(), CANONICAL.as_bytes());
    }
    eprintln!(
        "WORK retained {}",
        json!([
            owned,
            capacity,
            size_of::<guard::Remote>(),
            size_of::<OnceCell<String>>()
        ])
    );
    eprintln!(
        "TRACE ordinary-run {}",
        json!({"id":CANONICAL,"guards":512,"current_only":256})
    );
}
