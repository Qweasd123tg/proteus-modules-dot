// Compile alongside the official markdown 1.0.0 crate. No network, UI, or link handling.
use markdown::{
    Options, ParseOptions,
    mdast::{LinkReference, Node, ReferenceKind},
    to_html_with_options, to_mdast,
};
fn find(n: &Node) -> Option<&LinkReference> {
    if let Node::LinkReference(r) = n {
        return Some(r);
    }
    n.children()?.iter().find_map(find)
}
fn spelling<'s>(source: &'s str, r: &LinkReference) -> Option<&'s str> {
    let pos = r.position.as_ref()?;
    let raw = source.get(pos.start.offset..pos.end.offset)?;
    match r.reference_kind {
        ReferenceKind::Full => {
            let content_end = match r.children.last() {
                Some(child) => child.position()?.end.offset,
                None => pos.start.offset + 1,
            };
            source
                .get(content_end..pos.end.offset)?
                .strip_prefix("][")?
                .strip_suffix(']')
        }
        ReferenceKind::Shortcut => raw.strip_prefix('[')?.strip_suffix(']'),
        ReferenceKind::Collapsed => raw.strip_prefix('[')?.strip_suffix("][]"),
    }
}
fn html(s: &str) -> String {
    to_html_with_options(s, &Options::gfm()).unwrap()
}
fn test(fragment: &str, definition_label: &str, visible: &str, style: &str) -> (bool, bool) {
    let def = format!("\n\n[{definition_label}]: /guide \"Handbook\"\n");
    let source = format!("P {fragment} Q{def}");
    let md = to_mdast(&source, &ParseOptions::gfm()).unwrap();
    let r =
        find(&md).unwrap_or_else(|| panic!("native parser did not accept original {}", fragment));
    let original = html(&source);
    assert!(original.contains("href=\"/guide\" title=\"Handbook\""));
    let label = spelling(&source, r).expect("expected lexical reference label");
    assert_eq!(label, definition_label);
    let copied = format!("[{style}{visible}{style}][{label}]");
    let have = html(&format!("{copied}{def}"));
    let expected = html(&format!("[{style}{visible}{style}](/guide \"Handbook\")"));
    assert_eq!(have.trim_end(), expected.trim_end());
    let standalone = html(&copied);
    assert!(!standalone.contains("<a "));
    let other = html(&format!("{copied}\n\n[{definition_label}]: /other"));
    assert!(other.contains("href=\"/other\""));
    // Reproduce the two spelling choices using the values of the REAL mdast node.
    let caption = format!("{style}{visible}{style}");
    let old = match &r.label {
        Some(l) => format!("[{caption}]( \"{l}\")"),
        None => format!("[{caption}]()"),
    };
    let normalized = format!("[{caption}][{}]", r.identifier);
    let eq = |frag: String| html(&format!("{frag}{def}")).trim_end() == expected.trim_end();
    (eq(old), eq(normalized))
}
fn main() {
    let mut count = 0;
    let mut base = 0;
    let mut rejected = 0;
    for id in [
        "Manual",
        "A B C",
        "A &amp; B",
        r"Part \[A\]",
        r"File \\ part",
        "Два слова",
        "Straße",
        "İ",
        "ΐ",
        "a-b",
    ]
    .into_iter()
    .map(str::to_owned)
    .chain(["İ".repeat(340), "ΐ".repeat(200)])
    {
        for caption in [
            "the Guide",
            "the **Guide**",
            "the `Guide`",
            "the Guide ",
            r"the \*Guide\*",
            "the [Guide]",
        ] {
            let source = format!("[{caption}][{id}]");
            for style in ["", "**", "*", "`"] {
                let (a, b) = test(&source, &id, "Guide", style);
                base += u32::from(a);
                rejected += u32::from(b);
                count += 1;
            }
        }
    }
    for (caption, selected) in [
        ("the Guide", "Guide"),
        ("the `Guide`", "Guide"),
        ("the **Guide**", "Guide"),
        (r"A \[B\]", "B"),
        ("A &amp; B", "B"),
        ("A B C", "B"),
    ] {
        for kind in ["", "[]"] {
            let frag = format!("[{caption}]{kind}");
            for style in ["", "**", "*", "`"] {
                let (a, b) = test(&frag, caption, selected, style);
                base += u32::from(a);
                rejected += u32::from(b);
                count += 1;
            }
        }
    }
    println!(
        "Existing placeholder spelling: {base}/{count}. Rejected normalized-identifier spelling: {rejected}/{count}."
    );
    println!(
        "Official markdown-rs 1.0.0: {count}/{count} source-label extraction and same-definition target/title checks; no-definition unresolved and changed-definition rebound as expected. Not a clipboard implementation."
    );
}
