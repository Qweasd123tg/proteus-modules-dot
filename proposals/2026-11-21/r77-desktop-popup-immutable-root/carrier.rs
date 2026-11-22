// Test-only synchronous stand-ins for GPUI entities, windows, and process I/O.
use crate::declarative::protocol::{Incoming, Outgoing, SurfaceKind};
use crate::declarative::widget::Node;
use serde_json::Value;
use std::{
    cell::{Cell, RefCell},
    collections::HashMap,
    marker::PhantomData,
    path::PathBuf,
    rc::{Rc, Weak},
    time::{Duration, Instant},
};

#[derive(Default, Debug)]
struct Events {
    notify: usize,
    resize: usize,
    stop: usize,
    focus: Vec<u64>,
    restored: Vec<Option<u64>>,
}
struct Context<T> {
    events: Rc<RefCell<Events>>,
    kind: PhantomData<T>,
}
impl<T> Context<T> {
    fn new() -> Self {
        Self { events: Rc::default(), kind: PhantomData }
    }
    fn cast<U>(&self) -> Context<U> {
        Context { events: self.events.clone(), kind: PhantomData }
    }
    fn notify(&mut self) { self.events.borrow_mut().notify += 1; }
    fn emit(&mut self, _: WillResize) { self.events.borrow_mut().resize += 1; }
    fn stop_propagation(&mut self) { self.events.borrow_mut().stop += 1; }
}

#[derive(Clone, Debug)]
struct Focus(u64);
struct Window {
    focused: Option<Focus>,
    next: u64,
}
impl Window {
    fn focused<T>(&self, _: &Context<T>) -> Option<Focus> { self.focused.clone() }
}
impl Focus {
    fn focus<T>(&self, window: &mut Window, cx: &mut Context<T>) {
        cx.events.borrow_mut().focus.push(self.0);
        window.focused = Some(self.clone());
    }
}
struct Entity<T>(Rc<RefCell<T>>);
impl<T> Clone for Entity<T> {
    fn clone(&self) -> Self { Self(self.0.clone()) }
}
impl<T> Entity<T> {
    fn read<U>(&self, cx: &Context<U>) -> std::cell::Ref<'_, T> {
        let _ = cx;
        self.0.borrow()
    }
    fn update<U, R>(&self, cx: &mut Context<U>, f: impl FnOnce(&mut T, &mut Context<T>) -> R) -> R {
        f(&mut self.0.borrow_mut(), &mut cx.cast())
    }
}

#[derive(Clone)]
struct SurfaceView {
    view: ErasedView,
    focus: Focus,
}
#[derive(Clone)]
enum ErasedView { Declarative(Entity<DeclarativeView>), Other }
impl ErasedView {
    fn downcast<T: 'static>(self) -> Result<Entity<T>, ()> {
        match self {
            Self::Declarative(view) => {
                use std::any::Any;
                let erased: Box<dyn Any> = Box::new(view);
                erased.downcast::<Entity<T>>().map(|typed| *typed).map_err(|_| ())
            }
            Self::Other => Err(()),
        }
    }
}

#[derive(Default)]
struct Images {
    prepared: Vec<(usize, usize)>,
}
impl Images {
    fn prepare(&mut self, root: &Node, _: &Context<DeclarativeView>) {
        let mut n = 0;
        root.visit(&mut |_| n += 1);
        self.prepared.push((root as *const Node as usize, n));
    }
}
struct WillResize;

#[derive(Clone)]
struct ActionSink(Rc<RefCell<Vec<Value>>>);
impl ActionSink {
    fn read<T>(&self, _: &Context<T>) -> &Self { self }
    fn send(&self, message: &Outgoing) {
        self.0.borrow_mut().push(serde_json::to_value(message).unwrap());
    }
}
#[derive(Clone)]
struct Host {
    session: PathBuf,
    sender: ActionSink,
    titles: Rc<RefCell<Vec<(String, String)>>>,
    foreign_surface: bool,
}
impl Host {
    fn document_title<T>(&self, argument: &str, title: String, _: &Context<T>) {
        self.titles.borrow_mut().push((argument.into(), title));
    }
}

struct DeclarativeView {
    runtime: ActionSink,
    view: String,
    root: Option<Rc<Node>>,
    failure: Option<String>,
    images: Images,
    root_revision: u64,
    keys: HashMap<String, String>,
    action_sequence: u64,
    resize_on_reply: bool,
    source_revision: Option<u64>,
    accepted_source_revision: Option<u64>,
    focus_page: bool,
}
impl DeclarativeView {
    fn new(runtime: ActionSink, view: String) -> Self {
        Self {
            runtime, view, root: None, failure: None, images: Images::default(),
            root_revision: 0, keys: HashMap::new(), action_sequence: 0,
            resize_on_reply: false, source_revision: None, accepted_source_revision: None,
            focus_page: false,
        }
    }
    fn node(&self, root: &Node, path: &str, _: &mut Context<Self>) -> (Node, String) {
        // Structural parity trace only; measured pointer identities are collected before this read.
        (root.clone(), path.into())
    }
}
include!("view.inc.rs");
include!("view-readers.inc.rs");

struct Bounds<T>(PhantomData<T>);
struct Pixels;
#[derive(Clone, Copy)]
struct ResolvedPosition;
// Unobserved interpolation only; no rendering/raster code in this harness.
fn ease_out_cubic(t: f32) -> f32 { 1. - (1. - t).powi(3) }
include!("motion.inc.rs");

mod motion {
    use super::*;
    pub(super) fn restore_focus<T>(_: &Focus, to: Option<Focus>, window: &mut Window, cx: &mut Context<T>) {
        cx.events.borrow_mut().restored.push(to.as_ref().map(|focus| focus.0));
        window.focused = to;
    }
}

struct DeclarativeBadge {
    host: Host,
    popup: Popup<SurfaceView>,
    restore: Option<Focus>,
    // EXACT SLOT
}
fn surface<T>(host: Host, kind: SurfaceKind, argument: Option<String>, window: &mut Window, _: &mut Context<T>) -> SurfaceView {
    assert_eq!(kind, SurfaceKind::Popup);
    assert!(argument.is_none());
    window.next += 1;
    let view = if host.foreign_surface { ErasedView::Other } else {
        ErasedView::Declarative(Entity(Rc::new(RefCell::new(DeclarativeView::new(
            host.sender, format!("popup@{}", window.next),
        )))))
    };
    SurfaceView { view, focus: Focus(window.next) }
}
include!("popup.inc.rs");

// Exposes the exact production `.view.upgrade()` callback shape.
struct WeakView(Weak<RefCell<DeclarativeView>>);
impl WeakView {
    fn upgrade(&self) -> Option<Entity<DeclarativeView>> { self.0.upgrade().map(Entity) }
}
struct Route {
    view: WeakView,
    surface: SurfaceKind,
    argument: Option<String>,
}
struct BadgeSpec { narrow: bool }
struct SurfaceSpec { badge: Option<BadgeSpec> }
struct Manifest { surfaces: SurfaceSpec }
struct Extension { manifest: Manifest }
struct Runtime {
    host: Host,
    extension: Extension,
    views: HashMap<String, Route>,
    error: Option<String>,
    finished: Vec<(String, Option<u64>)>,
}
enum Signal { Message(Incoming) }
impl Runtime {
    fn new(host: Host) -> Self {
        Self { host,
            extension: Extension { manifest: Manifest { surfaces: SurfaceSpec { badge: None } } },
            views: HashMap::new(), error: None, finished: Vec::new(),
        }
    }
    fn attach(&mut self, entity: &Entity<DeclarativeView>, surface: SurfaceKind, argument: Option<&str>) {
        let view = entity.0.borrow().view.clone();
        self.views.insert(view, Route {
            view: WeakView(Rc::downgrade(&entity.0)), surface, argument: argument.map(str::to_string),
        });
    }
    fn session_dir(&self, key: &str, _: &Context<Self>) -> Option<PathBuf> {
        self.views.contains_key(key).then(|| self.host.session.clone())
    }
    fn host_for(&self, _: &str) -> Option<&Host> { Some(&self.host) }
    fn content_finished(&mut self, key: &str, rev: Option<u64>, _: &Context<Self>) {
        self.finished.push((key.into(), rev));
    }
}
include!("runtime.inc.rs");

fn popup_view(badge: &DeclarativeBadge) -> Entity<DeclarativeView> {
    badge.popup.current().unwrap().view.clone().downcast().unwrap()
}
fn badge(host: Host) -> DeclarativeBadge {
    DeclarativeBadge { host, popup: Popup::default(), last_popup: None, restore: None }
}
fn wire(input: &Value, view: &str, session: &PathBuf) -> Incoming {
    let mut input = input.clone();
    input["view"] = serde_json::json!(view);
    input["session_dir"] = serde_json::json!(session);
    crate::declarative::protocol::parse(&input.to_string()).unwrap()
}
fn receive(runtime: &mut Runtime, input: &Value, target: &Entity<DeclarativeView>, cx: &mut Context<Runtime>) {
    let view = target.0.borrow().view.clone();
    let incoming = wire(input, &view, &runtime.host.session);
    runtime.handle(Signal::Message(incoming), cx);
}
fn choices(node: &Node) -> &[crate::declarative::graph::Choice] {
    let Node::Stack { children, .. } = node else { panic!("stack fixture"); };
    let Node::Picker { options, .. } = &children[0] else { panic!("picker fixture"); };
    options
}
fn payload(value: &Value) -> &str {
    if let Some(text) = value.as_str() { return text; }
    value["opaque"][1]["note"].as_str().unwrap()
}
fn ownership(from: &Node, to: &Node) -> (usize, usize, usize) {
    assert_eq!(from, to);
    let (mut labels, mut payloads) = (0, 0);
    for (old, new) in choices(from).iter().zip(choices(to)) {
        assert_eq!(old.label, new.label);
        assert_eq!(payload(&old.value), payload(&new.value));
        labels += usize::from(old.label.as_ptr() != new.label.as_ptr());
        payloads += usize::from(payload(&old.value).as_ptr() != payload(&new.value).as_ptr());
    }
    (usize::from(!std::ptr::eq(from, to)), labels, payloads)
}
fn expect_view(view: &Entity<DeclarativeView>, expected: &Rc<Node>, source: Option<u64>, revision: u64) {
    let view = view.0.borrow();
    assert_eq!(view.root.as_ref(), Some(expected));
    assert_eq!(view.accepted_source_revision, source);
    assert_eq!(view.root_revision, revision);
    assert_eq!(view.keys.get("enter").unwrap(), "submit");
}
fn expect_held_after_close(weak: &Weak<Node>, candidate: bool) {
    assert_eq!(weak.upgrade().is_some(), candidate, "closed cache must pin original only for retained-Rc candidate");
}
pub(crate) fn run() {
    let stamp = env!("R77_POPUP_PROBE_ARM");
    eprintln!("ARM {stamp}");
    let candidate = stamp.ends_with("/candidate");
    for line in include_str!("fixtures.jsonl").lines() {
        let test: Value = serde_json::from_str(line).unwrap();
        let case = test["case"].as_str().unwrap();
        let initial = &test["receive_initial"];
        let mut fresh = test["receive_fresh_after_action"].clone();
        let mut stale = test["receive_stale_after_action"].clone();
        if stale.is_null() {
            stale = fresh.clone();
            stale["sequence"] = 1.into();
        }
        let cycles = test["cycles_without_fresh_reply"].as_u64().unwrap();
        let sender = ActionSink(Rc::default());
        let host = Host { session: "/synthetic/chat".into(), sender: sender.clone(), titles: Rc::default(), foreign_surface: false };
        let mut routes = Runtime::new(host.clone());
        let mut badge = badge(host.clone());
        let mut window = Window { focused: Some(Focus(9)), next: 9 };
        let mut cx = Context::new();
        let mut rx = cx.cast();
        badge.toggle_popup(&mut window, &mut cx);
        let mut current = popup_view(&badge);
        let mut original_entity = Rc::downgrade(&current.0);
        routes.attach(&current, SurfaceKind::Popup, None);
        assert!(current.0.borrow().root.is_none());
        assert!(badge.last_popup.is_none());
        receive(&mut routes, initial, &current, &mut rx);
        let original = current.0.borrow().root.as_ref().unwrap().clone();
        let previous = Rc::downgrade(&original);
        let n = choices(&original).len();
        let expected = if candidate { (0, 0, 0) } else { (1, n, n) };
        let mut totals = (0, 0, 0);
        assert_eq!(choices(&original).iter().filter(|choice| choice.selected).count(), 1);

        for _ in 0..cycles {
            let old_generation = badge.popup.generation();
            let old = current.0.borrow().root.as_ref().unwrap().clone();
            badge.close_popup(&mut window, &mut cx);
            assert!(!badge.popup.is_open());
            assert!(badge.popup.current().is_none());
            assert!(badge.popup.value().is_some(), "inert exit retained by production Popup");
            assert_eq!(cx.events.borrow().restored.last(), Some(&Some(9)));
            {
                let slot = badge.last_popup.as_ref().unwrap();
                let cache_root: &Node = std::borrow::Borrow::borrow(&slot.0);
                let close = ownership(&old, cache_root);
                assert_eq!(close, expected);
                totals.0 += close.0;
                totals.1 += close.1;
                totals.2 += close.2;
                assert_eq!(slot.1.get("enter").unwrap(), "submit");
                // Exact snapshot/cache sequence does not share keys' owned payloads.
                assert_ne!(current.0.borrow().keys["enter"].as_ptr(), slot.1["enter"].as_ptr());
            }
            let old_entity = current;
            badge.toggle_popup(&mut window, &mut cx);
            current = popup_view(&badge);
            routes.attach(&current, SurfaceKind::Popup, None);
            assert_ne!(badge.popup.generation(), old_generation);
            assert!(!badge.popup.close_if(old_generation));
            assert!(!Rc::ptr_eq(&old_entity.0, &current.0));
            let new = current.0.borrow().root.as_ref().unwrap().clone();
            let slot = badge.last_popup.as_ref().unwrap();
            let cache_root: &Node = std::borrow::Borrow::borrow(&slot.0);
            let reopen = ownership(cache_root, &new);
            assert_eq!(reopen, expected);
            totals.0 += reopen.0;
            totals.1 += reopen.1;
            totals.2 += reopen.2;
            expect_view(&current, &original, None, 1);
            if old_generation == 1 {
                // A retained inert entity can still receive *its* old addressed
                // reply, independent of the newly reopened view and its seed.
                receive(&mut routes, &fresh, &old_entity, &mut rx);
                assert_ne!(old_entity.0.borrow().root.as_ref(), Some(&original));
                expect_view(&current, &original, None, 1);
            }
            let mut view = current.0.borrow_mut();
            assert_eq!(view.images.prepared.len(), 1);
            assert_eq!(view.images.prepared[0].1, 2);
            assert_ne!(view.keys["enter"].as_ptr(), slot.1["enter"].as_ptr());
            let rendered = view.observed_render(&mut rx.cast()).unwrap();
            assert_eq!(&rendered.0, original.as_ref());
            assert_eq!(rendered.1, "root");
        }
        assert!(original_entity.upgrade().is_none(), "distinct old view entity released even when root retained");
        // Pause before a reply: key lookup routes via the newly attached view, not the source entity.
        {
            let mut view = current.0.borrow_mut();
            observed_key(&mut view, Some("enter".into()), true, &mut rx.cast());
            assert!(sender.0.borrow().is_empty());
            observed_key(&mut view, Some("enter".into()), false, &mut rx.cast());
            let value = choices(&original)[1].value.clone();
            view.act("model".into(), Some(value.clone()), &mut rx.cast());
            assert_eq!(view.action_sequence, test["pending_action_sequence"].as_u64().unwrap());
            assert_eq!(sender.0.borrow()[0], serde_json::json!({"type":"action","sequence":1,"view":view.view,"action":"submit"}));
            assert_eq!(sender.0.borrow()[1], serde_json::json!({"type":"action","sequence":2,"view":view.view,"action":"model","value":value}));
            assert!(view.resize_on_reply);
            assert_eq!(cx.events.borrow().stop, 1);
        }
        let resize = cx.events.borrow().resize;
        receive(&mut routes, &stale, &current, &mut rx);
        expect_view(&current, &original, None, 1);
        assert!(current.0.borrow().resize_on_reply);
        assert_eq!(cx.events.borrow().resize, resize);
        {
            let view = current.0.borrow().view.clone();
            let message = wire(&fresh, &view, &PathBuf::from("/synthetic/another"));
            let finishes = routes.finished.len();
            routes.handle(Signal::Message(message), &mut rx);
            assert_eq!(routes.finished.len(), finishes);
        }
        expect_view(&current, &original, None, 1);
        // Detached old entity id cannot mutate the current popup.
        {
            let old = wire(&fresh, "popup@10", &host.session);
            routes.handle(Signal::Message(old), &mut rx);
            expect_view(&current, &original, None, 1);
        }
        // Content-bearing views use a separate source-revision gate; exact method
        // must refuse mismatched source before preparing images or accepting keys.
        current.0.borrow_mut().source_revision = Some(7);
        fresh["source_revision"] = 6.into();
        receive(&mut routes, &fresh, &current, &mut rx);
        expect_view(&current, &original, None, 1);
        assert_eq!(current.0.borrow().images.prepared.len(), 1);
        assert_eq!(cx.events.borrow().resize, resize);
        current.0.borrow_mut().failure = Some("old error".into());
        fresh["source_revision"] = 7.into();
        receive(&mut routes, &fresh, &current, &mut rx);
        {
            let view = current.0.borrow();
            let replacement = view.root.as_ref().unwrap();
            assert_ne!(replacement, &original);
            assert!(!Rc::ptr_eq(replacement, &original));
            assert_eq!(view.images.prepared.iter().map(|r| r.1).collect::<Vec<_>>(), [2, 2]);
            assert_eq!(view.root_revision, 2);
            assert_eq!(view.accepted_source_revision, Some(7));
            assert!(view.focus_page);
            assert!(view.failure.is_none());
            assert!(!view.resize_on_reply);
            assert_eq!(cx.events.borrow().resize, resize + 1);
        }

        drop(original);
        expect_held_after_close(&previous, candidate);
        badge.close_popup(&mut window, &mut cx);
        assert!(previous.upgrade().is_none(), "prior root released when generation cache is replaced");
        // A warm cache seeds once more; new views still get their own mutable lifecycle and action state.
        badge.toggle_popup(&mut window, &mut cx);
        let last_generation = badge.popup.generation();
        let reopened = popup_view(&badge);
        assert_eq!(reopened.0.borrow().action_sequence, 0);
        assert!(!reopened.0.borrow().focus_page);
        assert_ne!(reopened.0.borrow().root.as_ref().unwrap().as_ref(), &serde_json::from_value::<Node>(initial["root"].clone()).unwrap());

        // An empty replacement popup retains last cache instead of erasing it.
        let fallback_node = reopened.0.borrow_mut().root.take().unwrap();
        badge.close_popup(&mut window, &mut cx);
        assert!(badge.last_popup.is_some());
        badge.toggle_popup(&mut window, &mut cx);
        assert!(!badge.popup.close_if(last_generation));
        expect_view(&popup_view(&badge), &fallback_node, None, 1);
        // No cross-badge cache, including a different session on the same fake window.
        let mut other_host = host.clone();
        other_host.session = "/synthetic/second-badge".into();
        let mut independent = self::badge(other_host);
        independent.toggle_popup(&mut window, &mut cx);
        assert!(popup_view(&independent).0.borrow().root.is_none());
        assert!(independent.last_popup.is_none());

        // Closed, open, failed downcast and missing snapshot retain their control distinctions.
        let mut foreign = self::badge(Host { foreign_surface: true, ..host });
        foreign.last_popup = badge.last_popup.clone();
        foreign.toggle_popup(&mut window, &mut cx);
        assert!(foreign.popup.current().unwrap().view.clone().downcast::<DeclarativeView>().is_err());
        foreign.close_popup(&mut window, &mut cx);
        assert!(foreign.last_popup.is_some());
        original_entity = Rc::downgrade(&current.0);
        drop(current);
        assert!(original_entity.upgrade().is_none());

        let activity = cx.events.borrow();
        println!("PASS {case} options={n} cycles={cycles} sent={} finished={} notify={} resize={} focus={} restored={}",
            sender.0.borrow().len(), routes.finished.len(), activity.notify, activity.resize, activity.focus.len(), activity.restored.len());
        eprintln!("WORK {case} root_clones={} new_label_buffers={} new_payload_buffers={}", totals.0, totals.1, totals.2);
    }

    let first: Value = serde_json::from_str(include_str!("fixtures.jsonl").lines().next().unwrap()).unwrap();
    let mut bad_pick = first["receive_initial"].clone();
    bad_pick["root"]["children"][0]["options"][1]["value"] = bad_pick["root"]["children"][0]["options"][0]["value"].clone();
    let mut bad_field = first["receive_initial"].clone();
    bad_field["root"]["undefined"] = true.into();
    let parse = crate::declarative::protocol::parse;
    let duplicate = parse(&bad_pick.to_string()).unwrap_err();
    assert!(duplicate.to_string().contains("unique values"), "{duplicate:#}");
    assert!(parse(&bad_field.to_string()).is_err());
    println!("PASS exact protocol rejects duplicate picker options and unknown field");
}
