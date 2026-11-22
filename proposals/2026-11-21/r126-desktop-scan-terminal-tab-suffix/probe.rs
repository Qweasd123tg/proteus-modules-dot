#[cfg(test)]
include!("counter.rs");

#[cfg(test)]
use proteus_tabs as tabs;

#[cfg(test)]
mod ui {
    use crate::tabs;
    use serde_json::json;
    use std::cell::RefCell;
    use std::collections::BTreeSet;
    use std::hint::black_box;
    use std::marker::PhantomData;
    use std::ops::Deref;
    use std::rc::Rc;
    use tabs::{ChatSpaces, Edge, PaneId, TabLayout};

    #[derive(Default)]
    struct Group {
        windows: Vec<(u32, ChatSpaces)>,
    }
    #[derive(Default, Clone)]
    struct WindowGroup(Rc<RefCell<Group>>);
    include!("window.inc.rs");
    include!("oracle.inc.rs");

    struct Document {
        command: Option<&'static str>,
    }
    struct Manifest {
        id: &'static str,
        document: Option<Document>,
    }
    const TERMINAL: Manifest = Manifest {
        id: "terminal",
        document: Some(Document {
            command: Some("terminal.new"),
        }),
    };
    const ALT: Manifest = Manifest {
        id: "another-shell",
        document: Some(Document {
            command: Some("terminal.new"),
        }),
    };
    const OTHER_COMMAND: Manifest = Manifest {
        id: "viewer",
        document: Some(Document {
            command: Some("viewer.open"),
        }),
    };
    const NO_DOCUMENT: Manifest = Manifest {
        id: "stub",
        document: None,
    };
    struct App {
        order: Vec<&'static Manifest>,
        disabled: Vec<&'static str>,
    }
    fn app(order: &[&'static Manifest], disabled: &[&'static str]) -> App {
        App {
            order: order.into(),
            disabled: disabled.into(),
        }
    }
    mod extensions {
        use super::{App, Manifest};
        fn ordered(cx: &App) -> Vec<&'static Manifest> {
            cx.order.clone()
        }
        fn is_enabled(id: &str, cx: &App) -> bool {
            !cx.disabled.contains(&id)
        }
        include!("extensions.inc.rs");
    }

    struct Window;
    struct Context<T>(App, PhantomData<T>);
    impl<T> Deref for Context<T> {
        type Target = App;
        fn deref(&self) -> &App {
            &self.0
        }
    }
    struct Workspace {
        windows: WindowGroup,
        allow: bool,
        can_mount: bool,
        actions: Vec<String>,
    }
    impl Workspace {
        // Inert outcomes; never load/launch a terminal or a real extension.
        fn begin_navigation(&mut self, _cx: &mut Context<Self>) -> bool {
            self.actions.push("navigation".into());
            self.allow
        }
        fn ensure_document(
            &mut self,
            id: &str,
            _: &mut Window,
            _: &mut Context<Self>,
        ) -> Option<()> {
            self.actions.push(format!("ensure:{id}"));
            self.can_mount.then_some(())
        }
        fn show_tab_in(
            &mut self,
            id: &str,
            pane: Option<PaneId>,
            _: &mut Window,
            _: &mut Context<Self>,
        ) {
            self.actions
                .push(format!("show:{:?}:{id}", pane.map(|p| p.0)));
        }
    }
    include!("action.inc.rs");

    const MAIN: &str = "chat:/synthetic/основной";
    const SECOND: &str = "codex:other-opaque-session";
    const THIRD: &str = "chat:/synthetic/別 set";
    const FILE: &str = "files:/src/Unicode-名.rs";

    fn layout(root: Option<&str>, ids: &[&str], grid: bool) -> TabLayout {
        let mut tree = TabLayout::default();
        if let Some(root) = root {
            tree.open(root, |_| false);
        }
        tree.open(FILE, |_| false);
        if grid {
            tree.split(FILE, PaneId(0), Edge::Right);
        }
        for id in ids {
            tree.open(id, |_| false);
        }
        assert!(tree.validate().is_ok());
        tree
    }
    fn from_spaces(areas: Vec<ChatSpaces>) -> Workspace {
        assert!(areas.iter().all(|a| a.validate().is_ok()));
        Workspace {
            windows: WindowGroup(Rc::new(RefCell::new(Group {
                windows: areas
                    .into_iter()
                    .enumerate()
                    .map(|(n, a)| (n as u32, a))
                    .collect(),
            }))),
            allow: true,
            can_mount: true,
            actions: vec![],
        }
    }
    fn one(main: TabLayout) -> Workspace {
        let mut group = ChatSpaces::default();
        assert!(group.set_active(Some(MAIN), main));
        from_spaces(vec![group])
    }
    fn multi() -> Workspace {
        let mut first = ChatSpaces::default();
        assert!(first.set_active(
            None,
            layout(None, &["terminal:+27", "another-shell:3"], false)
        ));
        let mut main = layout(
            Some(MAIN),
            &["terminal:2", "terminal:00029", "another-shell:5"],
            true,
        );
        main.open("terminal:900", |_| false);
        main.close("terminal:900");
        assert!(main.closed_ids().any(|id| id == "terminal:900"));
        main.open_preview("terminal:32", |_| false);
        assert_eq!(main.preview.as_deref(), Some("terminal:32"));
        assert!(first.set_active(Some(MAIN), main));
        assert!(first.set_active(Some(SECOND), layout(Some(SECOND), &["terminal:52"], false)));
        assert!(first.select(MAIN));

        let mut second = ChatSpaces::default();
        assert!(second.set_active(
            Some(MAIN),
            layout(
                Some(MAIN),
                &[
                    "terminal:2",
                    "terminal:73",
                    "terminal:٧",
                    "terminal: 999",
                    "terminal:4294967296",
                    "terminal:999/file"
                ],
                true
            )
        ));
        let mut third = ChatSpaces::default();
        assert!(third.set_active(
            Some(THIRD),
            layout(
                Some(THIRD),
                &["terminal:68", "terminal:+76", "another-shell:6"],
                true
            )
        ));
        assert!(third.set_active(Some("codex:detached-root"), TabLayout::default()));
        assert!(third.select(THIRD));
        from_spaces(vec![first, second, third])
    }

    fn saved(w: &Workspace) -> String {
        serde_json::to_string(&w.windows.0.borrow().windows).unwrap()
    }
    fn assert_membership(w: &Workspace) -> BTreeSet<String> {
        let actual = w.windows.baseline_all_tabs();
        let old = actual
            .panes()
            .into_iter()
            .flat_map(|p| p.tabs.iter().cloned())
            .collect::<BTreeSet<_>>();
        let windows = w.windows.0.borrow();
        let raw = windows
            .windows
            .iter()
            .flat_map(|(_, area)| area.all_tabs().map(str::to_owned))
            .collect::<BTreeSet<_>>();
        assert_eq!(old, raw, "legacy synth must preserve precise live ID union");
        old
    }
    fn scenario(label: &str, w: Workspace, cx: &App, want: Option<&str>, n: usize) {
        let before = saved(&w);
        let ids = assert_membership(&w);
        assert_eq!(w.resolve_terminal(cx).as_deref(), want);
        let (hits, calls, bytes) = crate::measurement(|| {
            (0..n)
                .filter(|_| black_box(&w).resolve_terminal(black_box(cx)).as_deref() == want)
                .count()
        });
        assert_eq!(hits, n);
        assert_eq!(saved(&w), before);
        eprintln!(
            "TRACE {label} {}",
            json!({"result":want,"union":ids,"windows":before,"tries":n})
        );
        eprintln!("WORK {label} {}", json!([n, ids.len(), calls, bytes]));
    }

    #[test]
    fn actual_saved_tab_union_and_normal_one_two_three_window_scans() {
        eprintln!("ARM {}", env!("R126_ARM"));
        let cx = app(&[&TERMINAL], &[]);
        scenario(
            "no-windows",
            from_spaces(vec![]),
            &cx,
            Some("terminal:1"),
            32,
        );
        scenario(
            "empty-window",
            from_spaces(vec![ChatSpaces::default()]),
            &cx,
            Some("terminal:1"),
            32,
        );
        scenario(
            "ordinary-one",
            one(layout(
                Some(MAIN),
                &["terminal:1", "terminal:2", "files:README.md"],
                false,
            )),
            &cx,
            Some("terminal:3"),
            64,
        );
        let many = multi();
        let ids = assert_membership(&many);
        assert!(
            ids.contains("terminal:32")
                && ids.contains("terminal:+76")
                && !ids.contains("terminal:900")
        );
        assert!(!ids.contains("codex:detached-root"));
        let two = many.windows.0.borrow().windows[..2]
            .iter()
            .map(|(_, s)| s.clone())
            .collect();
        scenario(
            "ordinary-two",
            from_spaces(two),
            &cx,
            Some("terminal:74"),
            64,
        );
        scenario("ordinary-three", many, &cx, Some("terminal:77"), 64);
    }

    #[test]
    fn exact_manifest_filters_order_and_other_prefix() {
        let cx = app(&[&NO_DOCUMENT, &OTHER_COMMAND, &ALT, &TERMINAL], &[]);
        scenario("first-provider", multi(), &cx, Some("another-shell:7"), 16);
        let disabled = app(&[&ALT, &TERMINAL], &["another-shell"]);
        scenario(
            "enabled-provider",
            multi(),
            &disabled,
            Some("terminal:77"),
            16,
        );
        let absent = app(&[&NO_DOCUMENT, &OTHER_COMMAND, &TERMINAL], &["terminal"]);
        scenario("no-provider", multi(), &absent, None, 16);
    }

    #[test]
    fn retained_navigation_and_mount_guard_order_and_pane_forwarding() {
        let mut w = multi();
        let mut cx = Context(app(&[&TERMINAL], &[]), PhantomData);
        let mut win = Window;
        let mut observed = Vec::new();
        let mut act =
            |label, w: &mut Workspace, cx: &mut Context<Workspace>, expected: &[&str], pane| {
                w.open_terminal(pane, &mut win, cx);
                assert!(
                    w.actions
                        .iter()
                        .map(String::as_str)
                        .eq(expected.iter().copied()),
                    "{label}"
                );
                observed.push((label, std::mem::take(&mut w.actions)));
            };
        w.allow = false;
        act(
            "navigation-blocked",
            &mut w,
            &mut cx,
            &["navigation"],
            Some(PaneId(3)),
        );
        w.allow = true;
        cx.0.disabled.push("terminal");
        act("disabled", &mut w, &mut cx, &["navigation"], None);
        cx.0.disabled.clear();
        w.can_mount = false;
        act(
            "mount-rejected",
            &mut w,
            &mut cx,
            &["navigation", "ensure:terminal:77"],
            None,
        );
        w.can_mount = true;
        act(
            "mount-then-show",
            &mut w,
            &mut cx,
            &[
                "navigation",
                "ensure:terminal:77",
                "show:Some(3):terminal:77",
            ],
            Some(PaneId(3)),
        );
        act(
            "default-pane",
            &mut w,
            &mut cx,
            &["navigation", "ensure:terminal:77", "show:None:terminal:77"],
            None,
        );
        eprintln!("TRACE navigation {}", json!(observed));
    }

    #[test]
    fn numeric_limits_and_malformed_suffixes_unchanged() {
        let cx = app(&[&TERMINAL], &[]);
        scenario(
            "bounds",
            one(layout(
                Some(MAIN),
                &[
                    "terminal:4294967294",
                    "terminal:-2",
                    "terminal:1:2",
                    "terminal: 42",
                    "terminal:",
                    "terminal:4294967296",
                    "terminal:２",
                    "terminal:+1",
                    "terminal:00007",
                ],
                false,
            )),
            &cx,
            Some("terminal:4294967295"),
            16,
        );
        let w = one(layout(Some(MAIN), &["terminal:4294967295"], false));
        assert_membership(&w);
        let wrapped =
            std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| w.resolve_terminal(&cx)));
        if cfg!(debug_assertions) {
            assert!(
                wrapped.is_err(),
                "legacy debug overflow on max must not be silently changed"
            );
        } else {
            assert_eq!(wrapped.unwrap().as_deref(), Some("terminal:0"));
        }
        eprintln!(
            "TRACE numeric-overflow {}",
            json!({"debug_overflow":cfg!(debug_assertions)})
        );
    }
}
