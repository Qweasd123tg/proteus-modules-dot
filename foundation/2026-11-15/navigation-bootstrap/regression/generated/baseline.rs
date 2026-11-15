// Proposed std-only source-extraction controls. NOT COMPILED OR RUN.
// Runtime methods are copied verbatim by generate.py. Host/transport/GPUI are
// synthetic stand-ins; these controls do not execute native focus or Files.
#[cfg(test)]
mod harness {
    use std::cell::RefCell;
    use std::collections::HashMap;
    use std::path::PathBuf;
    use std::rc::Rc;

    struct App;
    #[derive(Clone, Copy, PartialEq, Eq)]
    enum Lifetime { Workspace, Settings, Preview }
    impl Lifetime {
        fn session(self) -> bool { self == Self::Workspace }
    }
    #[derive(Clone, Debug, PartialEq, Eq)]
    enum HostEventKind { NavigationChanged }
    #[derive(Clone, Debug, PartialEq, Eq)]
    enum Outgoing {
        Context { context: String, workspace: PathBuf, session_dir: Option<PathBuf> },
        SessionSnapshot { context: String, session_dir: Option<PathBuf>, entries: bool },
        Event { context: String, event: HostEventKind, session_dir: Option<PathBuf>, document: Option<String> },
    }
    #[derive(Clone)]
    struct Host {
        context: String,
        session: Option<PathBuf>,
        workspace: Option<PathBuf>,
        document: Option<String>,
    }
    impl Host {
        fn session_dir(&self, _: &App) -> Option<PathBuf> { self.session.clone() }
        fn workspace_path(&self, _: &App) -> Option<PathBuf> { self.workspace.clone() }
        fn active_document(&self, _: &App) -> Option<String> { self.document.clone() }
        fn session_snapshot(&self, entries: bool, _: &App) -> Outgoing {
            Outgoing::SessionSnapshot { context: self.context.clone(), session_dir: self.session.clone(), entries }
        }
    }
    struct Scope { host: Host, session: Option<PathBuf>, workspace: PathBuf, announced: bool }
    struct Manifest { session_events: bool, session_entries: bool }
    struct Installed { manifest: Manifest }
    struct Process(Rc<RefCell<Vec<Outgoing>>>);
    impl Process {
        fn send(&self, message: &Outgoing) -> Result<(), ()> {
            self.0.borrow_mut().push(message.clone());
            Ok(())
        }
    }
    struct Runtime {
        lifetime: Lifetime,
        scopes: HashMap<String, Scope>,
        process: Option<Process>,
        extension: Installed,
    }
    impl Runtime {
    pub(super) fn announce_scope(&mut self, context: &str, cx: &App) {
        let Some(scope) = self.scopes.get(context) else {
            return;
        };
        let host = scope.host.clone();
        let session = self
            .lifetime
            .session()
            .then(|| host.session_dir(cx))
            .flatten();
        let snapshot_known = self
            .scopes
            .iter()
            .any(|(id, scope)| id != context && scope.announced && scope.session == session);
        let workspace = if !self.lifetime.session() {
            PathBuf::new()
        } else {
            host.workspace_path(cx).unwrap_or_default()
        };
        self.send(&Outgoing::Context {
            context: context.into(),
            workspace: workspace.clone(),
            session_dir: session.clone(),
        });
        if self.lifetime.session() && self.extension.manifest.session_events && !snapshot_known {
            self.send(&host.session_snapshot(self.extension.manifest.session_entries, cx));
        }
        if let Some(scope) = self.scopes.get_mut(context) {
            scope.session = session;
            scope.workspace = workspace;
            scope.announced = true;
        }
    }
    pub(super) fn reset_scopes(&mut self) {
        for scope in self.scopes.values_mut() {
            scope.announced = false;
        }
    }
    pub(super) fn send(&self, message: &Outgoing) {
        if let Some(process) = &self.process {
            // Transport failure is also delivered through the priority pump;
            // it closes the process and reports the error to every surface.
            let _ = process.send(message);
        }
    }
    }

    fn scope(context: &str, session: &str, document: Option<&str>) -> Scope {
        Scope {
            host: Host { context: context.into(), session: Some(session.into()),
                workspace: Some("/fixture/project".into()), document: document.map(str::to_owned) },
            session: None, workspace: PathBuf::new(), announced: false,
        }
    }
    fn fixture(lifetime: Lifetime, session_events: bool) -> (Runtime, Rc<RefCell<Vec<Outgoing>>>) {
        let output = Rc::new(RefCell::new(Vec::new()));
        let runtime = Runtime {
            lifetime,
            scopes: HashMap::from([("a".into(), scope("a", "/fixture/session", Some("visible.rs")))]),
            process: Some(Process(output.clone())),
            extension: Installed { manifest: Manifest { session_events, session_entries: true } },
        };
        (runtime, output)
    }
    fn navigation(context: &str, session: &str, document: Option<&str>) -> Outgoing {
        Outgoing::Event { context: context.into(), event: HostEventKind::NavigationChanged,
            session_dir: Some(session.into()), document: document.map(str::to_owned) }
    }

    #[test]
    fn initial_scope_orders_context_snapshot_then_navigation() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, true);
        runtime.announce_scope("a", &App);
        assert_eq!(*output.borrow(), vec![
            Outgoing::Context { context: "a".into(), workspace: "/fixture/project".into(), session_dir: Some("/fixture/session".into()) },
            Outgoing::SessionSnapshot { context: "a".into(), session_dir: Some("/fixture/session".into()), entries: true },
            navigation("a", "/fixture/session", Some("visible.rs")),
        ]);
        assert!(runtime.scopes["a"].announced);
    }

    #[test]
    fn no_snapshot_subscription_still_gets_navigation() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, false);
        runtime.announce_scope("a", &App);
        assert_eq!(output.borrow().len(), 2);
        assert_eq!(output.borrow().last(), Some(&navigation("a", "/fixture/session", Some("visible.rs"))));
    }

    #[test]
    fn absent_active_document_is_not_guessed_from_a_retained_view() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, false);
        runtime.scopes.get_mut("a").unwrap().host.document = None;
        runtime.announce_scope("a", &App);
        assert_eq!(output.borrow().last(), Some(&navigation("a", "/fixture/session", None)));
    }

    #[test]
    fn deferred_prelaunch_announcement_cannot_suppress_real_bootstrap() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, true);
        runtime.process = None;
        runtime.announce_scope("a", &App);
        assert!(output.borrow().is_empty());
        assert!(!runtime.scopes["a"].announced);
        // Preserve the existing metadata bookkeeping, even before transport.
        assert_eq!(runtime.scopes["a"].session, Some("/fixture/session".into()));
        runtime.process = Some(Process(output.clone()));
        runtime.announce_scope("a", &App);
        assert_eq!(output.borrow().last(), Some(&navigation("a", "/fixture/session", Some("visible.rs"))));
    }

    #[test]
    fn restart_reseeds_current_not_previous_navigation() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, true);
        runtime.announce_scope("a", &App);
        runtime.process = None;
        runtime.reset_scopes();
        runtime.scopes.get_mut("a").unwrap().host.document = Some("new.rs".into());
        output.borrow_mut().clear();
        runtime.process = Some(Process(output.clone()));
        runtime.announce_scope("a", &App);
        assert_eq!(output.borrow().len(), 3);
        assert_eq!(output.borrow().last(), Some(&navigation("a", "/fixture/session", Some("new.rs"))));
    }

    #[test]
    fn already_announced_scope_does_not_duplicate_navigation() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, true);
        runtime.announce_scope("a", &App);
        output.borrow_mut().clear();
        runtime.scopes.get_mut("a").unwrap().host.session = Some("/fixture/next".into());
        runtime.announce_scope("a", &App);
        // The caller's existing SessionOpened event supplies navigation.
        // This harness exercises announce_scope only, not that caller/GPUI.
        assert_eq!(output.borrow().len(), 2);
        assert!(!output.borrow().iter().any(|message| matches!(message, Outgoing::Event { .. })));
        assert_eq!(runtime.scopes["a"].session, Some("/fixture/next".into()));
    }

    #[test]
    fn shared_session_deduplicates_snapshot_not_context_navigation() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, true);
        runtime.announce_scope("a", &App);
        output.borrow_mut().clear();
        runtime.scopes.insert("b".into(), scope("b", "/fixture/session", Some("other.rs")));
        runtime.announce_scope("b", &App);
        assert_eq!(output.borrow().len(), 2);
        assert!(!output.borrow().iter().any(|message| matches!(message, Outgoing::SessionSnapshot { .. })));
        assert_eq!(output.borrow().last(), Some(&navigation("b", "/fixture/session", Some("other.rs"))));
    }

    #[test]
    fn different_session_still_receives_its_own_snapshot() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, true);
        runtime.announce_scope("a", &App);
        output.borrow_mut().clear();
        runtime.scopes.insert("b".into(), scope("b", "/fixture/other-session", None));
        runtime.announce_scope("b", &App);
        assert_eq!(output.borrow().len(), 3);
        assert!(matches!(&output.borrow()[1], Outgoing::SessionSnapshot { context, .. } if context == "b"));
        assert_eq!(output.borrow().last(), Some(&navigation("b", "/fixture/other-session", None)));
    }

    #[test]
    fn non_session_lifetimes_keep_context_only() {
        for lifetime in [Lifetime::Settings, Lifetime::Preview] {
            let (mut runtime, output) = fixture(lifetime, true);
            runtime.announce_scope("a", &App);
            assert_eq!(*output.borrow(), vec![Outgoing::Context {
                context: "a".into(), workspace: PathBuf::new(), session_dir: None,
            }]);
        }
    }

    #[test]
    fn missing_context_is_a_noop() {
        let (mut runtime, output) = fixture(Lifetime::Workspace, true);
        runtime.announce_scope("missing", &App);
        assert!(output.borrow().is_empty());
    }
}
