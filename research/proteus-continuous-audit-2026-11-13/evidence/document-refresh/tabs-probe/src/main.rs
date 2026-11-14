use proteus_tabs::{TabLayout, PaneId, Edge, split_document};
use serde_json::{Value, json};
fn active_document(layout: &TabLayout) -> Option<String> {
    // Exact selection expression from native Host::active_document, after
    // lifetime/workspace ownership checks. No GPUI or Host shim is executed.
    let (owner, argument) = split_document(layout.active(layout.focused)?)?;
    (owner == "files").then(|| argument.to_string())
}
fn snapshot(layout: &TabLayout) -> Value {
    json!({"visible":layout.visible().collect::<Vec<_>>(),
           "focused_pane":layout.focused.0,
           "active_document":active_document(layout),
           "layout":layout})
}
fn main() {
    let mut layout=TabLayout::default();
    for file in ["files:left.rs", "files:hidden.rs", "files:right.rs"] {
        layout.open(file, |_| false);
    }
    layout.split("files:right.rs", PaneId(0), Edge::Right);
    layout.activate(PaneId(0), "files:left.rs");
    layout.validate().unwrap();
    assert_eq!(layout.visible().collect::<Vec<_>>(), vec!["files:left.rs", "files:right.rs"]);
    let two_documents=snapshot(&layout);
    layout.focus(PaneId(1));
    let right_focused=snapshot(&layout);
    layout.focus(PaneId(0));
    layout.open("chat:/fixture/session", |_| false);
    layout.validate().unwrap();
    assert_eq!(layout.visible().collect::<Vec<_>>(), vec!["chat:/fixture/session", "files:right.rs"]);
    let chat_and_document=snapshot(&layout);
    println!("{}",serde_json::to_string_pretty(&json!({"two_documents":two_documents,"right_focused":right_focused,"chat_and_document":chat_and_document})).unwrap());
}
