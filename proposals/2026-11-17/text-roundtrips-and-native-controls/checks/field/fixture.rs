#![allow(dead_code, private_interfaces)]
use std::marker::PhantomData;
use std::{
    cell::RefCell,
    collections::HashMap,
    ops::{Deref, DerefMut},
    rc::Rc,
};
#[derive(Clone, Debug, Default)]
struct SharedString(String);
impl AsRef<str> for SharedString {
    fn as_ref(&self) -> &str {
        &self.0
    }
}
impl Deref for SharedString {
    type Target = str;
    fn deref(&self) -> &str {
        &self.0
    }
}
impl std::fmt::Display for SharedString {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.0.fmt(f)
    }
}
#[derive(Default)]
struct App {
    next: u64,
}
#[derive(Default)]
struct Window {
    focused: Option<u64>,
}
#[derive(Clone, Copy)]
struct FocusHandle(u64);
impl FocusHandle {
    fn is_focused(&self, w: &Window) -> bool {
        w.focused == Some(self.0)
    }
    fn focus(&self, w: &mut Window, _: &mut App) {
        w.focused = Some(self.0)
    }
}
struct Context<T>(App, PhantomData<T>);
impl<T> Deref for Context<T> {
    type Target = App;
    fn deref(&self) -> &App {
        &self.0
    }
}
impl<T> DerefMut for Context<T> {
    fn deref_mut(&mut self) -> &mut App {
        &mut self.0
    }
}
impl<T> Default for Context<T> {
    fn default() -> Self {
        Self(App::default(), PhantomData)
    }
}
struct Entity<U>(Rc<RefCell<U>>);
impl<U> Clone for Entity<U> {
    fn clone(&self) -> Self {
        Self(self.0.clone())
    }
}
impl<U> Entity<U> {
    fn read(&self, _: &App) -> std::cell::Ref<'_, U> {
        self.0.borrow()
    }
    fn update<V>(&self, cx: &mut App, f: impl FnOnce(&mut U, &mut App) -> V) -> V {
        f(&mut self.0.borrow_mut(), cx)
    }
}
impl<T> Context<T> {
    fn new<U>(&mut self, f: impl FnOnce(&mut Context<U>) -> U) -> Entity<U> {
        let mut c = Context::<U>::default();
        std::mem::swap(&mut self.0, &mut c.0);
        let u = f(&mut c);
        std::mem::swap(&mut self.0, &mut c.0);
        Entity(Rc::new(RefCell::new(u)))
    }
    fn subscribe<U>(
        &mut self,
        _: &Entity<U>,
        _: impl FnMut(&mut T, Entity<U>, &InputEvent, &mut Context<T>) + 'static,
    ) -> Subscription {
        Subscription
    }
}
struct Subscription;
enum InputEvent {
    Change,
    PressEnter { secondary: bool },
}
#[derive(Default)]
struct State {
    id: u64,
    text: SharedString,
    row_min: usize,
    row_max: usize,
}
type InputState = State;
type TextareaState = State;
impl State {
    fn new(_: &mut Window, cx: &mut Context<Self>) -> Self {
        cx.next += 1;
        Self {
            id: cx.next,
            ..Default::default()
        }
    }
    fn placeholder(self, _: String) -> Self {
        self
    }
    fn set_placeholder(&mut self, _: String, _: &mut Window, _: &mut App) {}
    fn set_value(&mut self, x: String, _: &mut Window, _: &mut App) {
        self.text = SharedString(x)
    }
    fn value(&self) -> SharedString {
        self.text.clone()
    }
    fn auto_grow(mut self, r: usize, m: usize) -> Self {
        self.row_min = r;
        self.row_max = m;
        self
    }
    fn focus_handle(&self, _: &App) -> FocusHandle {
        FocusHandle(self.id)
    }
}
mod textarea {
    use super::*;
    pub fn max_rows(s: &str, min: usize, g: bool) -> usize {
        if g {
            s.chars().count().saturating_add(1).max(min)
        } else {
            min
        }
    }
    pub fn resize(e: &Entity<State>, min: usize, g: bool, c: &mut App) {
        e.update(c, |x, _| {
            x.row_min = min;
            x.row_max = max_rows(&x.text, min, g)
        })
    }
    pub fn disclosure_id(x: &str) -> String {
        format!("input-preview:{x}")
    }
    pub fn preview(_: &str) -> Option<String> {
        None
    }
}
#[macro_export]
macro_rules! fake_json {
    ($x:expr) => {
        $x
    };
}
mod serde_json {
    pub(crate) use crate::fake_json as json;
}
//IMPL_TEXT
// Minimal values and entity bookkeeping only; no native widget or callback delivery.
enum Node {
    Input {
        id: String,
        value: String,
        placeholder: String,
        action: String,
        lines: usize,
        submit: Option<String>,
        search: bool,
    },
}
#[derive(Default)]
struct Fields {
    inputs: HashMap<String, TextInput>,
    disclosures: HashMap<String, bool>,
}
#[derive(Default)]
struct DeclarativeView {
    fields: Fields,
}
impl DeclarativeView {
    fn act(&mut self, _: String, _: Option<String>, _: &mut Context<Self>) {}
    fn refresh(
        &mut self,
        node: &Node,
        settings: bool,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        match node{
//INPUT_ARM
}
    }
}
fn node(lines: usize, search: bool, value: &str) -> Node {
    assert!((1..=40).contains(&lines) && (!search || lines == 1));
    Node::Input {
        id: "filter".into(),
        value: value.into(),
        placeholder: String::new(),
        action: "edit".into(),
        lines,
        submit: None,
        search,
    }
}
fn present(v: &DeclarativeView, search: bool, c: &App) -> (&'static str, usize, u64) {
    match &v.fields.inputs["filter"].state {
        Text::Line(x) => (if search { "Search" } else { "Line" }, 1, x.read(c).id),
        Text::Area(x) => (
            if search { "Empty" } else { "Area" },
            x.read(c).row_min,
            x.read(c).id,
        ),
    }
}
fn main() {
    use std::collections::BTreeMap;
    let states = [
        (1, false),
        (1, true),
        (2, false),
        (4, false),
        (8, false),
        (40, false),
    ];
    let mut errors = BTreeMap::new();
    for &(n, s) in &states {
        for &(m, t) in &states {
            for settings in [false, true] {
                for focus in [false, true] {
                    for (old, live, new, want) in [
                        ("Draft", "Draft", "Remote", "Remote"),
                        ("Draft", "Локально", "Draft", "Локально"),
                    ] {
                        let mut w = Window::default();
                        let mut c = Context::default();
                        let mut v = DeclarativeView::default();
                        v.refresh(&node(n, s, old), settings, &mut w, &mut c);
                        let input = &v.fields.inputs["filter"];
                        let old_id = input.state.focus_handle(&c).0;
                        if focus {
                            w.focused = Some(old_id)
                        }
                        input.state.set_value(live.into(), &mut w, &mut c);
                        v.refresh(&node(m, t, new), settings, &mut w, &mut c);
                        let (kind, rows, id) = present(&v, t, &c);
                        let expected = if t {
                            "Search"
                        } else if m == 1 {
                            "Line"
                        } else {
                            "Area"
                        };
                        for (key, ok) in [
                            ("visible kind", kind == expected),
                            ("rows", rows == m),
                            (
                                "draft value",
                                v.fields.inputs["filter"].state.value(&c).as_ref() == want,
                            ),
                            ("compatible entity", (n == 1) != (m == 1) || id == old_id),
                            (
                                "focus retained",
                                w.focused == if focus { Some(id) } else { None },
                            ),
                        ] {
                            *errors.entry(key).or_insert(0) += usize::from(!ok)
                        }
                        if n == 4 && m == 1 && t && settings && focus && new == "Remote" {
                            println!(
                                "four-row field -> valid single-line search: {kind} (expected Search)"
                            );
                        }
                    }
                }
            }
        }
    }
    println!(
        "6 x 6 descriptors, settings/panel x focused/not x remote/local = 288 transitions; failure counts: {errors:?}"
    );
    assert!(errors.values().all(|e| *e == 0));
}
