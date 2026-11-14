
// Audit-only regressions, not a production change.
fn trace_refresh_chain(all: bool) -> Vec<Line> {
    let before = workspace(&[
        ("", &[("src", true)]),
        ("src", &[("lib", true)]),
        ("src/lib", &[("existing.rs", false)]),
    ]);
    let after = workspace(&[
        ("", &[("src", true)]),
        ("src", &[("lib", true), ("new.rs", false)]),
        ("src/lib", &[("existing.rs", false)]),
    ]);
    let mut project = Project::default();
    let initial = project.lines("project", &mut loader(&before)).unwrap();
    assert_eq!(initial[1].path, "src/lib");
    if all { project.expand_all("src/lib", &mut loader(&before)); }
    else { project.expand("src/lib", &mut loader(&before)); }
    let opened = project.lines("project", &mut loader(&before)).unwrap();
    assert!(opened.iter().any(|line| line.path == "src/lib/existing.rs"));
    project.invalidate(false);
    project.lines("project", &mut loader(&after)).unwrap();
    project.invalidate(false);
    project.lines("project", &mut loader(&after)).unwrap()
}

#[test]
fn trace_folded_expand_all_must_reload_chain_ancestors() {
    let lines = trace_refresh_chain(true);
    assert!(lines.iter().any(|line| line.path == "src/new.rs"), "new sibling remains invisible: {lines:?}");
}

#[test]
fn trace_folded_regular_expand_reloads_chain_ancestors() {
    let lines = trace_refresh_chain(false);
    assert!(lines.iter().any(|line| line.path == "src/new.rs"));
}

fn trace_transient_listing(failed: &str) -> Vec<Line> {
    let folders = workspace(&[("", &[("src", true)]), ("src", &[("visible.rs", false)])]);
    let mut project = Project::default();
    project.lines("project", &mut loader(&folders)).unwrap();
    project.expand("src", &mut loader(&folders));
    assert!(project.lines("project", &mut loader(&folders)).unwrap().iter().any(|line| line.path == "src/visible.rs"));
    project.invalidate(false);
    let mut failures = 0;
    let mut fail_once = |path: &str| -> Result<Listing> {
        if path == failed && failures == 0 {
            failures += 1;
            Err(proteus_extension::anyhow!("temporary failure"))
        } else { loader(&folders)(path) }
    };
    let error_pass = project.lines("project", &mut fail_once);
    assert_eq!(failures, 1);
    assert_eq!(error_pass.is_err(), failed.is_empty());
    project.invalidate(false);
    project.lines("project", &mut loader(&folders)).unwrap();
    project.invalidate(false);
    project.lines("project", &mut loader(&folders)).unwrap()
}

#[test]
fn trace_nested_listing_recovers_after_one_transient_failure() {
    let lines = trace_transient_listing("src");
    assert!(lines.iter().any(|line| line.path == "src/visible.rs"), "healthy API no longer retried: {lines:?}");
}

#[test]
fn trace_root_listing_recovers_after_one_transient_failure() {
    let lines = trace_transient_listing("");
    assert!(lines.iter().any(|line| line.path == "src/visible.rs"));
}
