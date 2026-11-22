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
include!("active.inc.rs");

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
    eprintln!("ARM {}", env!("R122_ARM"));
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

const LEFT: &str = "chat:/fixture/левый";
const RIGHT: &str = "codex:opaque:right";
const LOWER: &str = "files:/é/日.txt";
const OTHER: &str = "chat:/fixture/😀";
const INACTIVE: &str = "files:/inactive";
const MISSING: &str = "files:/missing";

fn grid() -> TabLayout {
    use tabs::{Edge, PaneId};
    let mut l = TabLayout::default();
    l.open(LEFT, |_| false);
    l.open_in(RIGHT, PaneId(0), |_| false);
    l.split(RIGHT, PaneId(0), Edge::Right);
    l.open_in(LOWER, PaneId(0), |_| false);
    l.split(LOWER, PaneId(0), Edge::Bottom);
    l.open_in(OTHER, PaneId(1), |_| false);
    l.split(OTHER, PaneId(1), Edge::Bottom);
    l.open_in(INACTIVE, PaneId(0), |_| false);
    l.activate(PaneId(0), LEFT);
    assert_eq!(l.pane_count(), 4);
    assert!(l.validate().is_ok());
    l
}

fn with_layout(layout: TabLayout, keys: &[&str], settings: bool) -> Workspace {
    Workspace {
        api: Some(Api(1)),
        settings: settings.then_some(()),
        documents: keys
            .iter()
            .map(|id| ((*id).to_owned(), SurfaceView { view: View(ENTITY) }))
            .collect(),
        layout,
        parked_spaces: HashMap::new(),
    }
}

fn expected_visibility(w: &Workspace, id: &str, entity: EntityId) -> bool {
    // Unchanged ordered reporting API is an independent membership oracle.
    if w.settings.is_some() || !w.layout.visible().any(|active| active == id) {
        return false;
    }
    w.documents.get(id).map(|s| s.view.0) == Some(entity)
}

#[test]
fn workspace_visible_matches_ordered_active_oracle_with_live_locked_and_settings() {
    let mut l = grid();
    let before = l.visible().map(str::to_owned).collect::<Vec<_>>();
    assert_eq!(before.len(), 4);
    assert!(
        l.pane(tabs::PaneId(0))
            .unwrap()
            .tabs
            .iter()
            .any(|id| id == INACTIVE)
    );
    assert!(!before.iter().any(|id| id == INACTIVE));
    l.lock_pane(tabs::PaneId(1), true, 1200., 800., 0.);
    assert_eq!(l.pane_locked(tabs::PaneId(1)), Some(true));
    assert_eq!(l.visible().collect::<Vec<_>>(), before);
    let saved = serde_json::to_string(&l).unwrap();
    let mut w = with_layout(l, &[LEFT, RIGHT, LOWER, INACTIVE], false);
    let queries = [
        (LEFT, ENTITY, true),
        (RIGHT, ENTITY, true),
        (LOWER, ENTITY, true),
        (OTHER, ENTITY, false),
        (INACTIVE, ENTITY, false),
        (MISSING, ENTITY, false),
        (LEFT, ENTITY + 1, false),
        ("files:/e\u{301}/日.txt", ENTITY, false),
    ];
    for (id, entity, expect) in queries {
        assert_eq!(expected_visibility(&w, id, entity), expect, "{id}");
        assert_eq!(w.document_visible(id, entity), expect, "{id}");
    }
    assert!(w.document_current(INACTIVE, ENTITY));
    assert!(!w.document_visible(INACTIVE, ENTITY));
    w.documents.insert(
        LEFT.into(),
        SurfaceView {
            view: View(ENTITY + 1),
        },
    );
    assert!(!w.document_visible(LEFT, ENTITY));
    assert!(w.document_visible(LEFT, ENTITY + 1));
    w.settings = Some(());
    assert!(!w.document_visible(LEFT, ENTITY + 1));
    assert!(w.document_current(LEFT, ENTITY + 1));
    assert_eq!(serde_json::to_string(&w.layout).unwrap(), saved);
    eprintln!(
        "TRACE ordinary-split {}",
        json!({
            "queries":queries, "active":before, "layout":saved,
            "old_entity_visible":false, "new_entity_visible":true, "settings_visible":false
        })
    );
}

#[test]
fn odd_tree_preserves_leaf_active_not_general_tab_membership() {
    let pane = |id, tabs: &[&str], active: Option<&str>| json!({"pane":{"id":id,"tabs":tabs,"pinned":0,"active":active}});
    let node = |n| json!({"size":{"weight":1.},"node":n});
    let split = |children| json!({"split":{"axis":"row","children":children}});
    let repeated = "chat:duplicate";
    let unlisted = "files:active-but-not-in-own-tabs";
    let leafs = vec![
        node(pane(0, &[repeated, LEFT], Some(LEFT))),
        node(split(vec![])),
        node(split(vec![
            node(pane(0, &[repeated], Some(repeated))),
            node(pane(1, &[], Some(""))),
            node(pane(2, &[MISSING], Some(unlisted))),
            node(pane(3, &[INACTIVE], None)),
        ])),
    ];
    let decode = |root| {
        serde_json::from_value::<TabLayout>(json!({"root":root,"focused":0,"next_id":4})).unwrap()
    };
    let l = decode(split(leafs));
    assert!(l.validate().is_err()); // intentionally transient in-memory shape
    assert_eq!(
        l.visible().collect::<Vec<_>>(),
        [LEFT, repeated, "", unlisted]
    );
    let w = with_layout(l, &[LEFT, repeated, "", unlisted, MISSING, INACTIVE], false);
    let cases = [
        (LEFT, true),
        (repeated, true),
        ("", true),
        (unlisted, true),
        (MISSING, false),
        (INACTIVE, false),
    ];
    for (id, expected) in cases {
        assert_eq!(expected_visibility(&w, id, ENTITY), expected);
        assert_eq!(w.document_visible(id, ENTITY), expected);
    }
    let no_leaves = with_layout(decode(split(vec![])), &[""], false);
    let default_none = with_layout(TabLayout::default(), &[""], false);
    assert!(!no_leaves.document_visible("", ENTITY));
    assert!(!default_none.document_visible("", ENTITY));
    eprintln!(
        "TRACE transient-tree {}",
        json!({"cases":cases,"no_leaves":false,"none":false})
    );
}

#[test]
fn exact_document_guard_allocations_independent_of_terminal_key() {
    let ordinary = model(CANONICAL, ENTITY, Some(1), true, false, false);
    let covered = model(CANONICAL, ENTITY, Some(1), true, true, false);
    let multi = with_layout(grid(), &[LEFT, RIGHT, LOWER, OTHER, MISSING], false);
    let order = multi.layout.visible().collect::<Vec<_>>();
    let states = [
        ("direct-single", ordinary.as_ref(), CANONICAL, true),
        ("direct-grid-first", &multi, order[0], true),
        ("direct-grid-last", &multi, order[3], true),
        ("direct-grid-miss", &multi, MISSING, false),
        ("direct-settings", covered.as_ref(), CANONICAL, false),
    ];
    let mut trace = Vec::new();
    for (label, w, id, expected) in states {
        assert_eq!(expected_visibility(w, id, ENTITY), expected);
        let (seen, calls, bytes) = crate::measurement(|| {
            (0..256)
                .filter(|_| black_box(w).document_visible(black_box(id), ENTITY))
                .count()
        });
        assert_eq!(seen, if expected { 256 } else { 0 });
        eprintln!("WORK {label} {}", json!([256, seen, calls, bytes]));
        trace.push((label, expected, seen));
    }
    eprintln!("TRACE direct-guard {}", json!(trace));
}
