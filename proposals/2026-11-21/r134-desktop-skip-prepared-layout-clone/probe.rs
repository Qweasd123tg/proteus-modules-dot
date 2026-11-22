#[cfg(test)]
include!("counter.rs");

#[cfg(test)]
mod focused {
    use proteus_tabs::{ChatSpaces, Edge, PaneId, TabLayout};
    use serde_json::{Value, json};
    use std::cell::RefCell;
    use std::future::{Future, poll_fn, ready};
    use std::hint::black_box;
    use std::marker::PhantomData;
    use std::path::{Path, PathBuf};
    use std::pin::Pin;
    use std::rc::Rc;
    use std::task::{Context as PollContext, Poll, Waker};

    // Only the two lifted functions execute product control flow. These
    // deterministic boundaries never create a native window, OS worker, HTTP
    // server/client, application event loop, or real startup operation.
    mod anyhow {
        macro_rules! anyhow {
            ($message:literal) => {
                $message.to_owned()
            };
        }
        pub(super) use anyhow;
    }
    type Result<T> = std::result::Result<T, String>;
    type Task<T> = Pin<Box<dyn Future<Output = T>>>;
    type Log = Rc<RefCell<Vec<&'static str>>>;
    type Applied = Rc<RefCell<Option<Result<Boot>>>>;
    type Deferred = Box<dyn FnOnce(&mut Workspace, &mut Window, &mut Context<Workspace>)>;
    const PROJECT: &str = "/fixture/workspace";
    const OTHER: &str = "/fixture/other";

    #[derive(Debug)]
    struct Boot {
        tag: &'static str,
        spaces: Option<ChatSpaces>,
    }

    fn record(log: &Log, what: &'static str) {
        log.borrow_mut().push(what);
    }

    #[derive(Clone)]
    struct Target;
    #[derive(Clone, Copy, PartialEq, Eq)]
    enum StartupIntent {
        Restore,
        Fresh,
    }
    struct LaunchOptions {
        workspace: PathBuf,
        target: Target,
        startup: StartupIntent,
        log: Log,
    }
    struct Window;
    struct Preferences(ChatSpaces);
    impl Preferences {
        fn spaces_for(&self, path: &Path, _: &Target) -> ChatSpaces {
            assert_eq!(path, Path::new(PROJECT));
            self.0.clone()
        }
    }
    mod prefs {
        use super::{Context, Preferences, Workspace};
        pub(super) fn current(cx: &Context<Workspace>) -> &Preferences {
            &cx.prefs
        }
    }

    struct Context<T> {
        log: Log,
        prefs: Preferences,
        applied: Applied,
        deferred: Option<Deferred>,
        target: PhantomData<T>,
    }
    impl Context<Workspace> {
        fn new(spaces: ChatSpaces) -> Self {
            Self {
                log: Log::default(),
                prefs: Preferences(spaces),
                applied: Applied::default(),
                deferred: None,
                target: PhantomData,
            }
        }

        fn defer_in(
            &mut self,
            _: &mut Window,
            f: impl FnOnce(&mut Workspace, &mut Window, &mut Context<Workspace>) + 'static,
        ) {
            record(&self.log, "defer-before-paint");
            assert!(self.deferred.replace(Box::new(f)).is_none());
        }
        fn spawn_in<F>(
            &mut self,
            _: &mut Window,
            f: impl FnOnce(WeakWorkspace, AsyncContext) -> F,
        ) -> Task<()>
        where
            F: Future<Output = ()> + 'static,
        {
            record(&self.log, "spawn-in");
            Box::pin(f(
                WeakWorkspace,
                AsyncContext {
                    log: self.log.clone(),
                    applied: self.applied.clone(),
                },
            ))
        }
    }

    struct AsyncContext {
        log: Log,
        applied: Applied,
    }
    struct Background;
    impl AsyncContext {
        fn background_executor(&self) -> Background {
            record(&self.log, "background-executor");
            Background
        }
    }
    impl Background {
        fn spawn<T>(&self, f: impl Future<Output = T>) -> impl Future<Output = T> {
            f
        }
    }
    struct WeakWorkspace;
    impl WeakWorkspace {
        fn update_in(
            &self,
            cx: AsyncContext,
            f: impl FnOnce(&mut Workspace, &mut Window, &mut Context<Workspace>),
        ) -> std::result::Result<(), ()> {
            record(&cx.log, "entity-update");
            let mut proxy = Context::new(ChatSpaces::default());
            proxy.log = cx.log;
            proxy.applied = cx.applied;
            f(
                &mut Workspace {
                    spaces: ChatSpaces::default(),
                    _startup: None,
                },
                &mut Window,
                &mut proxy,
            );
            Ok(())
        }
    }

    struct WindowGroup;
    impl WindowGroup {
        fn new(path: &Path, _: &Target) -> Self {
            assert_eq!(path, Path::new(PROJECT));
            Self
        }
    }
    struct Workspace {
        spaces: ChatSpaces,
        _startup: Option<Task<()>>,
    }
    impl Workspace {
        fn empty(
            _: PathBuf,
            _: Target,
            spaces: ChatSpaces,
            _: WindowGroup,
            _: &mut Window,
            cx: &mut Context<Self>,
        ) -> Self {
            // Match the actual unmutated layout/move order. The materializer
            // asserts its independently cloned active layout and registration.
            let _layout = spaces.active_layout().clone();
            let _registered = spaces.clone();
            record(&cx.log, "registered-empty");
            Self {
                spaces,
                _startup: None,
            }
        }
        fn finish_startup(&mut self, value: Result<Boot>, _: &mut Window, cx: &mut Context<Self>) {
            record(&cx.log, "finish");
            assert!(cx.applied.borrow_mut().replace(value).is_none());
        }
    }
    fn boot(options: &LaunchOptions, spaces: ChatSpaces) -> Result<Boot> {
        assert_eq!(options.workspace, Path::new(PROJECT));
        record(&options.log, "boot");
        if options.startup == StartupIntent::Fresh {
            assert_eq!(spaces, ChatSpaces::default());
        }
        Ok(Boot {
            tag: "inert-fallback",
            spaces: Some(spaces),
        })
    }
    struct Mailbox {
        state: Option<Result<Boot>>,
        closed: bool,
    }
    struct Receiver {
        mailbox: Rc<RefCell<Mailbox>>,
        log: Log,
    }
    impl Receiver {
        fn try_recv(&self) -> std::result::Result<Result<Boot>, ()> {
            record(&self.log, "try-recv");
            self.mailbox.borrow_mut().state.take().ok_or(())
        }
        async fn recv(&self) -> std::result::Result<Result<Boot>, ()> {
            poll_fn(|_| {
                record(&self.log, "recv-poll");
                let mut state = self.mailbox.borrow_mut();
                if let Some(value) = state.state.take() {
                    Poll::Ready(Ok(value))
                } else if state.closed {
                    Poll::Ready(Err(()))
                } else {
                    Poll::Pending
                }
            })
            .await
        }
    }
    impl Drop for Receiver {
        fn drop(&mut self) {
            record(&self.log, "receiver-drop");
        }
    }
    mod async_channel {
        pub(super) type Receiver<T> = super::TypedReceiver<T>;
    }
    struct TypedReceiver<T> {
        inner: Receiver,
        payload: PhantomData<T>,
    }
    impl<T> std::ops::Deref for TypedReceiver<T> {
        type Target = Receiver;
        fn deref(&self) -> &Self::Target {
            &self.inner
        }
    }
    mod startup {
        use super::{Boot, PathBuf, Result, async_channel};
        pub(super) struct Preparation {
            pub(super) workspace: PathBuf,
            pub(super) result: async_channel::Receiver<Result<Boot>>,
        }
        // Keep exact original visibility inside its module; only this method
        // is compiled from the complete untouched production startup source.
        use std::path::Path;
        include!("match.inc.rs");
    }
    use startup::Preparation;
    mod workspace {
        use super::*;
        include!("construct.inc.rs");
    }

    struct BorrowedWorkspace<'a> {
        spaces: &'a ChatSpaces,
    }
    include!("clone.inc.rs");

    fn restored(live: bool) -> ChatSpaces {
        let mut spaces = ChatSpaces::default();
        for branch in 0..=4 {
            let root = format!("chat:/fixture/комната-{branch}");
            let mut layout = TabLayout::default();
            layout.open(&root, |_| false);
            for n in 1..=13 {
                layout.open(
                    &format!("files:/fixtures/{branch}-{n}-слой-日本語.txt"),
                    |_| false,
                );
            }
            let split = format!("files:/fixtures/{branch}-13-слой-日本語.txt");
            layout.split(&split, PaneId(0), Edge::Right);
            if branch < 2 {
                layout.open(
                    &format!("files:/fixtures/{branch}-ordinary-extra.txt"),
                    |_| false,
                );
            }
            if live {
                // Stress beyond deserialized prefs: revive real nonserialized
                // recent-close and activation history through public methods.
                let gone = format!("files:/fixtures/{branch}-just-closed.txt");
                layout.open(&gone, |_| false);
                layout.close(&gone);
                assert_eq!(layout.closed_ids().next(), Some(gone.as_str()));
            }
            assert_eq!(layout.validate(), Ok(()));
            assert!(spaces.set_active((branch != 0).then_some(root.as_str()), layout));
        }
        assert_eq!(spaces.all_tabs().count(), 72);
        assert_eq!(spaces.roots().count(), 4);
        if live {
            return spaces;
        }
        let raw = serde_json::to_vec(&spaces).unwrap();
        assert_ne!(spaces, serde_json::from_slice::<ChatSpaces>(&raw).unwrap());
        serde_json::from_slice(&raw).unwrap()
    }

    fn option(cx: &Context<Workspace>, startup: StartupIntent) -> LaunchOptions {
        LaunchOptions {
            workspace: PROJECT.into(),
            target: Target,
            startup,
            log: cx.log.clone(),
        }
    }
    fn prepare(
        cx: &Context<Workspace>,
        path: &str,
        state: Option<Result<Boot>>,
        closed: bool,
    ) -> (Preparation, Rc<RefCell<Mailbox>>) {
        let mailbox = Rc::new(RefCell::new(Mailbox { state, closed }));
        (
            Preparation {
                workspace: path.into(),
                result: TypedReceiver {
                    inner: Receiver {
                        mailbox: mailbox.clone(),
                        log: cx.log.clone(),
                    },
                    payload: PhantomData,
                },
            },
            mailbox,
        )
    }
    fn prepared(tag: &'static str) -> Result<Boot> {
        Ok(Boot { tag, spaces: None })
    }
    fn poll(task: &mut Task<()>) -> Poll<()> {
        task.as_mut()
            .poll(&mut PollContext::from_waker(Waker::noop()))
    }
    fn trace(label: &str, cx: &Context<Workspace>, actions: &[&str], result: Value) {
        assert_eq!(&*cx.log.borrow(), actions);
        eprintln!(
            "TRACE {label} {}",
            json!({"actions": actions, "result": result})
        );
    }

    const READY: &[&str] = &[
        "registered-empty",
        "try-recv",
        "defer-before-paint",
        "receiver-drop",
        "finish",
    ];

    #[test]
    fn buffered_success_and_error_remain_deferred() {
        eprintln!("ARM {}", env!("R134_ARM"));
        for (label, result, expected) in [
            ("ready-ok", prepared("first-ready"), "first-ready"),
            (
                "ready-error",
                Err("synthetic startup error".into()),
                "synthetic startup error",
            ),
        ] {
            let spaces = restored(false);
            let mut cx = Context::new(spaces.clone());
            let (p, _) = prepare(&cx, PROJECT, Some(result), true);
            let mut w = Workspace::new(
                option(&cx, StartupIntent::Restore),
                Some(p),
                &mut Window,
                &mut cx,
            );
            assert_eq!(w.spaces, spaces);
            assert!(w._startup.is_none() && cx.applied.borrow().is_none());
            cx.deferred.take().unwrap()(&mut w, &mut Window, &mut cx);
            let applied = cx.applied.borrow_mut().take().unwrap();
            let tag = match &applied {
                Ok(value) => value.tag,
                Err(error) => error.as_str(),
            };
            assert_eq!(tag, expected);
            trace(label, &cx, READY, json!([applied.is_ok(), tag]));
        }
    }

    #[test]
    fn pending_ready_or_error_and_closed_channels_never_boot() {
        for (label, before_closed, delivered, expected) in [
            (
                "pending-ok",
                false,
                Some(prepared("later-ready")),
                "later-ready",
            ),
            (
                "pending-error",
                false,
                Some(Err("later startup error".into())),
                "later startup error",
            ),
            ("closed-later", false, None, "startup preparation stopped"),
            ("already-closed", true, None, "startup preparation stopped"),
        ] {
            let spaces = restored(false);
            let mut cx = Context::new(spaces.clone());
            let (p, mailbox) = prepare(&cx, PROJECT, None, before_closed);
            let mut w = Workspace::new(
                option(&cx, StartupIntent::Restore),
                Some(p),
                &mut Window,
                &mut cx,
            );
            assert_eq!(w.spaces, spaces);
            assert!(cx.deferred.is_none() && cx.applied.borrow().is_none());
            let mut task = w._startup.take().unwrap();
            if !before_closed {
                assert_eq!(poll(&mut task), Poll::Pending);
                assert!(cx.applied.borrow().is_none());
                let mut mailbox = mailbox.borrow_mut();
                mailbox.closed = true;
                mailbox.state = delivered;
            }
            assert_eq!(poll(&mut task), Poll::Ready(()));
            let applied = cx.applied.borrow_mut().take().unwrap();
            let tag = match &applied {
                Ok(value) => value.tag,
                Err(error) => error.as_str(),
            };
            assert_eq!(tag, expected);
            let mut actions = vec!["registered-empty", "try-recv", "spawn-in", "recv-poll"];
            if !before_closed {
                actions.push("recv-poll");
            }
            actions.extend(["receiver-drop", "entity-update", "finish"]);
            trace(label, &cx, &actions, json!([applied.is_ok(), tag]));
        }
        let mut cx = Context::new(restored(false));
        let (p, _mailbox) = prepare(&cx, PROJECT, None, false);
        let mut w = Workspace::new(
            option(&cx, StartupIntent::Restore),
            Some(p),
            &mut Window,
            &mut cx,
        );
        let mut task = w._startup.take().unwrap();
        assert_eq!(poll(&mut task), Poll::Pending);
        drop(task);
        assert!(cx.applied.borrow().is_none());
        trace(
            "cancelled-pending",
            &cx,
            &[
                "registered-empty",
                "try-recv",
                "spawn-in",
                "recv-poll",
                "receiver-drop",
            ],
            json!(null),
        );
    }

    #[test]
    fn fallback_captures_original_before_poll_and_discards_wrong_workspace() {
        for (label, mismatch, fresh) in [
            ("absent-preparation", false, false),
            ("wrong-workspace", true, false),
            ("fresh-fallback", false, true),
        ] {
            let spaces = restored(true);
            let expected = if fresh {
                ChatSpaces::default()
            } else {
                spaces.clone()
            };
            let mut cx = Context::new(spaces);
            let p = mismatch.then(|| prepare(&cx, OTHER, Some(prepared("must-not-use")), false).0);
            let intent = if fresh {
                StartupIntent::Fresh
            } else {
                StartupIntent::Restore
            };
            let mut w = Workspace::new(option(&cx, intent), p, &mut Window, &mut cx);
            assert_eq!(w.spaces, expected);
            assert!(cx.deferred.is_none() && cx.applied.borrow().is_none());
            // Synchronously captured layout must remain original even if the
            // actual workspace has already switched before fallback polls.
            assert!(w.spaces.select("chat:/fixture/replacement"));
            assert_ne!(w.spaces, expected);
            assert_eq!(poll(&mut w._startup.take().unwrap()), Poll::Ready(()));
            let applied = cx.applied.borrow_mut().take().unwrap().unwrap();
            assert_eq!(applied.tag, "inert-fallback");
            let got = applied.spaces.unwrap();
            assert_eq!(got, expected);
            let mut actions = vec!["registered-empty"];
            if mismatch {
                actions.push("receiver-drop");
            }
            actions.extend([
                "spawn-in",
                "background-executor",
                "boot",
                "entity-update",
                "finish",
            ]);
            // Equality/Debug witness MRU and recently closed IDs too.
            trace(
                label,
                &cx,
                &actions,
                json!([applied.tag, got, format!("{got:?}")]),
            );
        }
    }

    #[test]
    fn exact_branch_local_allocations() {
        let saved = restored(false);
        let live = restored(true);
        let empty = ChatSpaces::default();
        for (label, spaces, matched) in [
            ("matched-loaded", &saved, true),
            ("matched-live-stress", &live, true),
            ("matched-empty", &empty, true),
            ("fallback-loaded", &saved, false),
            ("fallback-live-stress", &live, false),
            ("fallback-empty", &empty, false),
        ] {
            let (copied, calls, bytes) = crate::measurement(|| {
                cloned_layout(black_box(spaces), black_box(matched.then_some(())))
            });
            if !matched {
                assert_eq!(&copied, spaces);
            }
            eprintln!("WORK {label} {}", json!([calls, bytes]));
        }
    }
}
