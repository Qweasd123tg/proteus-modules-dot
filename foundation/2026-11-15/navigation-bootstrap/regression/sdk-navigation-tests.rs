// Proposed addition to sdk/src/host/tests.rs in Extensions f82b3ad.
// Uses that module's existing super imports and real Host::handle, but a
// synthetic renderer with no API calls. NOT COMPILED OR RUN.
// These are consumer controls, not baseline-red producer regressions.

#[derive(Default)]
struct NavigationBootstrapProbe {
    rendered: Vec<(String, Option<String>, Option<Value>)>,
}

impl Extension for NavigationBootstrapProbe {
    fn render(&mut self, host: &mut Host, view: &str, _: Surface, _: Option<&str>) -> Result {
        self.rendered.push((view.into(), host.session.clone(), host.active_document.clone()));
        Ok(())
    }
}

#[test]
fn bootstrap_navigation_is_available_to_first_and_hidden_document_renders() {
    let mut host = Host::default();
    let mut extension = NavigationBootstrapProbe::default();
    host.handle(&mut extension, json!({"type":"context", "context":"window",
        "workspace":"/fixture/project", "session_dir":"/fixture/session"})).unwrap();
    host.handle(&mut extension, json!({"type":"event", "context":"window",
        "event":"navigation_changed", "session_dir":"/fixture/session", "document":"visible.rs"})).unwrap();
    assert!(extension.rendered.is_empty(), "bootstrap cannot render a view that is not registered");
    for (view, argument) in [("visible", "visible.rs"), ("hidden", "hidden.rs")] {
        host.handle(&mut extension, json!({"type":"render", "context":"window",
            "view":view, "surface":"document", "argument":argument, "session_dir":"/fixture/session"})).unwrap();
    }
    assert_eq!(extension.rendered, vec![
        ("visible".into(), Some("/fixture/session".into()), Some(json!("visible.rs"))),
        ("hidden".into(), Some("/fixture/session".into()), Some(json!("visible.rs"))),
    ]);
}

#[test]
fn shared_session_contexts_keep_independent_bootstrapped_documents() {
    let mut host = Host::default();
    let mut extension = NavigationBootstrapProbe::default();
    for (context, document) in [("left", "left.rs"), ("right", "right.rs")] {
        host.handle(&mut extension, json!({"type":"context", "context":context,
            "workspace":"/fixture/project", "session_dir":"/fixture/session"})).unwrap();
        if context == "left" {
            // Native bootstrap deduplicates this shared-session snapshot,
            // but document metadata is still sent for the second context.
            host.handle(&mut extension, json!({"type":"session_snapshot", "context":context,
                "session_dir":"/fixture/session", "state":{}, "entries":[]})).unwrap();
        }
        host.handle(&mut extension, json!({"type":"event", "context":context,
            "event":"navigation_changed", "session_dir":"/fixture/session", "document":document})).unwrap();
        host.handle(&mut extension, json!({"type":"render", "context":context,
            "view":context, "surface":"document", "argument":document, "session_dir":"/fixture/session"})).unwrap();
    }
    extension.rendered.clear();
    // A poll-style pass activates each stored view's context before rendering.
    host.render_every_context(&mut extension);
    assert_eq!(extension.rendered, vec![
        ("left".into(), Some("/fixture/session".into()), Some(json!("left.rs"))),
        ("right".into(), Some("/fixture/session".into()), Some(json!("right.rs"))),
    ]);
}

#[test]
fn navigation_without_document_clears_host_document_without_session_epoch_change() {
    let mut host = Host::default();
    let mut extension = NavigationBootstrapProbe::default();
    host.handle(&mut extension, json!({"type":"context", "context":"window",
        "workspace":"/fixture/project", "session_dir":"/fixture/session"})).unwrap();
    host.handle(&mut extension, json!({"type":"event", "context":"window",
        "event":"navigation_changed", "session_dir":"/fixture/session", "document":"old.rs"})).unwrap();
    let epoch = host.session_event_epoch;
    // Native Outgoing skips a None document field; the existing SDK clears it.
    host.handle(&mut extension, json!({"type":"event", "context":"window",
        "event":"navigation_changed", "session_dir":"/fixture/session"})).unwrap();
    host.handle(&mut extension, json!({"type":"render", "context":"window",
        "view":"retained", "surface":"document", "argument":"old.rs", "session_dir":"/fixture/session"})).unwrap();
    assert_eq!(extension.rendered.last(), Some(&("retained".into(), Some("/fixture/session".into()), None)));
    assert_eq!(host.session_event_epoch, epoch);
}
