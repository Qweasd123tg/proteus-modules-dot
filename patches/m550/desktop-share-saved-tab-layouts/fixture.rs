use crate::{ChatSpaces, Edge, TabLayout, meter};
use std::{
    cell::RefCell,
    hash::{DefaultHasher, Hash, Hasher},
    hint::black_box,
};

fn digest(data: &[u8]) -> u64 {
    let mut h = DefaultHasher::new();
    data.hash(&mut h);
    h.finish()
}

fn root(n: usize) -> String {
    if n % 7 == 6 {
        format!("codex:opaque:project:{n:03}")
    } else {
        format!("chat:/synthetic/repository/history/project-{n:03}")
    }
}
fn doc(n: usize, j: usize) -> String {
    format!("files:src/conversations/project-{n:03}/document-{j:03}/subsection/history_context.rs")
}
fn seed(roots: usize, files: usize, closed: usize) -> ChatSpaces {
    let mut spaces = ChatSpaces::default();
    for i in 0..roots {
        assert!(spaces.select(&root(i)));
        let mut layout = spaces.active_layout().clone();
        for j in 0..files {
            let id = doc(i, j);
            layout.open(&id, |_| false);
            if j % 7 == 6 {
                layout.split_active(Edge::Right);
            }
            if j % 8 == 5 {
                layout.set_pinned(&id, true);
            }
        }
        for j in files..(files + closed) {
            let id = doc(i, j);
            layout.open(&id, |_| false);
            layout.close(&id);
        }
        assert_eq!(layout.closed_ids().count(), closed);
        spaces.save_active(layout);
    }
    spaces.validate().unwrap();
    spaces
}

fn constructor(loaded: &ChatSpaces) -> (ChatSpaces, TabLayout, ChatSpaces) {
    // Product Workspace::new/empty owns a clone of scoped preferences,
    // a local active TabLayout, and the WindowGroup registration copy.
    let workspace = loaded.clone();
    let active = workspace.active_layout().clone();
    let registered = workspace.clone();
    (workspace, active, registered)
}

fn report(
    label: &str,
    count: meter::Count,
    loaded: &ChatSpaces,
    result: &ChatSpaces,
    wire_bytes: usize,
) {
    let text = serde_json::to_vec(result).unwrap();
    let shared = loaded
        .root_layouts()
        .zip(result.root_layouts())
        .filter(|((p, a), (q, b))| p == q && std::ptr::eq(*a, *b))
        .count();
    println!(
        "M406_TABS {label} {} {} {} {} {} {} {} {} {}",
        count.requests,
        count.bytes,
        count.live,
        count.peak,
        count.largest,
        wire_bytes,
        result.roots().count(),
        shared,
        digest(&text)
    );
}
fn cold(label: &str, roots: usize, files: usize) {
    let source = seed(roots, files, 0);
    let bytes = serde_json::to_vec(&source).unwrap();
    let (loaded, alloc) = meter::measure(|| serde_json::from_slice::<ChatSpaces>(&bytes).unwrap());
    loaded.validate().unwrap();
    assert!(
        loaded
            .all_layouts()
            .all(|layout| layout.closed_ids().next().is_none())
    );
    assert_eq!(serde_json::to_vec(&loaded).unwrap(), bytes);
    report(
        &format!("{label}-decode"),
        alloc,
        &source,
        &loaded,
        bytes.len(),
    );
    let ((workspace, layout, group), alloc) = meter::measure(|| constructor(&loaded));
    assert_eq!(loaded, workspace);
    assert_eq!(workspace, group);
    assert_eq!(&layout, loaded.active_layout());
    assert_eq!(serde_json::to_vec(&group).unwrap(), bytes);
    report(
        &format!("{label}-first-window"),
        alloc,
        &loaded,
        &group,
        bytes.len(),
    );
    black_box((&loaded, &workspace, &layout, &group));
}

#[test]
fn saved_layout_deserialization_and_exact_first_window_copy_chain() {
    cold("empty", 0, 0);
    cold("single", 1, 8);
    cold("mixed-areas", 64, 24);
}

#[test]
fn group_republish_shares_roots_until_edits_without_changing_order_or_navigation() {
    let previous = seed(50, 17, 5);
    let workspace = previous.clone();
    let before = serde_json::to_vec(&previous).unwrap();
    let ((group, outgoing, copy), alloc) = meter::measure(|| {
        // WindowGroup::persist's registered state; Group::saved_layout's
        // first window; and prefs::update's clone of the previous value.
        let group = workspace.clone();
        let outgoing = group.clone();
        let copy = previous.clone();
        (group, outgoing, copy)
    });
    assert_eq!(previous, group);
    assert_eq!(previous, outgoing);
    assert_eq!(previous, copy);
    report("live-republish", alloc, &previous, &outgoing, before.len());
    assert!(
        outgoing
            .root_layouts()
            .all(|(_, layout)| layout.closed_ids().count() == 5)
    );

    let mut edited = group;
    let id = root(10);
    let (ok, alloc) = meter::measure(|| {
        edited.retarget_document(&id, &doc(10, 5), "files:renamed-on-one-window")
    });
    assert!(ok);
    assert!(edited.contains("files:renamed-on-one-window"));
    assert!(!outgoing.contains("files:renamed-on-one-window"));
    assert_eq!(serde_json::to_vec(&previous).unwrap(), before);
    assert_eq!(serde_json::to_vec(&copy).unwrap(), before);
    assert_eq!(serde_json::to_vec(&outgoing).unwrap(), before);
    edited.validate().unwrap();
    report(
        "single-area-retarget",
        alloc,
        &outgoing,
        &edited,
        before.len(),
    );

    let mut detached = ChatSpaces::default();
    let mut fragment = TabLayout::default();
    fragment.open("terminal:fragment-in-another-window", |_| false);
    detached.set_active(Some(&id), fragment);
    let original = edited.clone();
    edited.include_window(&detached);
    assert!(edited.contains("terminal:fragment-in-another-window"));
    assert!(!original.contains("terminal:fragment-in-another-window"));
    let seen = RefCell::new(Vec::new());
    edited.retain_documents(|name| {
        seen.borrow_mut().push(name.to_owned());
        !name.contains("/document-006/")
    });
    assert!(!edited.contains(&doc(10, 6)));
    assert!(original.contains(&doc(10, 6)));
    edited.extract_chat_except(&root(9), &id);
    edited.remove_chats([root(11).as_str(), root(12).as_str()]);
    edited.validate().unwrap();
    original.validate().unwrap();
    assert_eq!(original.roots().count(), 50);
    assert_eq!(edited.roots().count(), 48);
    let bytes = serde_json::to_vec(&edited).unwrap();
    let hash = digest(&bytes);
    let order = digest(&serde_json::to_vec(&seen.into_inner()).unwrap());
    println!("M406_STATE {hash} {order}");
}
