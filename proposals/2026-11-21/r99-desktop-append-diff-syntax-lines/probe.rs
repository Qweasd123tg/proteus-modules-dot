extern crate proteus_diff as diff;
extern crate self as gpui_kit;

mod count;
mod syntax;

use diff::{File, FileInfo, Kind, Line};
use std::{
    cell::RefCell,
    fmt::Write,
    hash::{Hash, Hasher},
    ops::Range,
};

#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash)]
pub struct HighlightStyle(u8);
pub struct SharedString;
pub struct Div;
pub struct ElementId;
pub struct TextStyleRefinement {
    pub color: Option<()>,
}
impl Default for TextStyleRefinement {
    fn default() -> Self {
        Self { color: None }
    }
}
pub fn div() -> Div {
    Div
}
impl Div {
    fn absolute(self) -> Self {
        self
    }
    fn relative(self) -> Self {
        self
    }
    fn top_0(self) -> Self {
        self
    }
    fn left_0(self) -> Self {
        self
    }
    fn child<T>(self, _: T) -> Self {
        self
    }
}
pub fn transparent_black() {}
impl Clone for SharedString {
    fn clone(&self) -> Self {
        Self
    }
}
pub struct StyledText;
impl StyledText {
    fn new(_: SharedString) -> Self {
        Self
    }
    fn with_highlights(self, _: syntax::Highlights) -> Self {
        self
    }
}
pub mod base {
    use super::{ElementId, SharedString, TextStyleRefinement};
    pub struct SelectableText;
    impl SelectableText {
        pub fn new(_: ElementId, _: SharedString) -> Self {
            Self
        }
        pub fn text_style(self, _: TextStyleRefinement) -> Self {
            self
        }
    }
    pub mod input {
        pub struct Rope(pub String);
        impl Rope {
            pub fn from_str(s: &str) -> Self {
                Self(s.into())
            }
        }
    }
}
pub mod component {
    pub mod highlighter {
        use crate::{base::input::Rope, captured, modeled_styles};
        use std::ops::Range;

        pub struct HighlightTheme;
        pub struct SyntaxHighlighter(String);
        impl SyntaxHighlighter {
            pub fn new(language: &str) -> Self {
                Self(language.into())
            }
            pub fn update(&mut self, _old: Option<()>, rope: &Rope, _edits: Option<()>) {
                captured(|side| {
                    side.language.clone_from(&self.0);
                    side.source.clone_from(&rope.0);
                });
            }
            pub fn styles(
                &self,
                range: &Range<usize>,
                _: &HighlightTheme,
            ) -> crate::syntax::Highlights {
                captured(|side| {
                    assert_eq!(range, &(0..side.source.len()));
                    modeled_styles(&side.source)
                })
            }
        }
    }
}

#[derive(Default)]
struct Side {
    work: count::Work,
    source: String,
    ranges: Vec<Option<Range<usize>>>,
    language: String,
}
thread_local! {
    static CAPTURE: RefCell<Vec<Side>> = const { RefCell::new(Vec::new()) };
}
fn remember_ranges(ranges: &[Option<Range<usize>>]) {
    let work = count::stop();
    CAPTURE.with_borrow_mut(|sides| {
        sides.push(Side {
            work,
            ranges: ranges.to_vec(),
            ..Side::default()
        })
    });
}
fn captured<R>(f: impl FnOnce(&mut Side) -> R) -> R {
    CAPTURE.with_borrow_mut(|sides| f(sides.last_mut().unwrap()))
}
fn modeled_styles(source: &str) -> syntax::Highlights {
    let mut spans = Vec::new();
    let mut at = 0;
    for (i, (b, _)) in source.char_indices().enumerate() {
        if i > 0 && i % 7 == 0 {
            spans.push((at..b, HighlightStyle((spans.len() % 3 + 1) as u8)));
            at = b;
        }
    }
    if at < source.len() {
        spans.push((
            at..source.len(),
            HighlightStyle((spans.len() % 3 + 1) as u8),
        ));
    }
    spans
}

fn expected(file: &File, old: bool) -> (String, Vec<Option<Range<usize>>>) {
    let mut result = String::new();
    let mut positions = Vec::new();
    for row in &file.lines {
        match (&row.kind, old) {
            (Kind::Hunk, _) => {
                result.push('\n');
                positions.push(None);
            }
            (Kind::Note, _) | (Kind::Added, true) | (Kind::Removed, false) => positions.push(None),
            _ => {
                let start = result.len();
                result += &row.text.replace('\t', "    ");
                positions.push(Some(start..result.len()));
                result.push('\n');
            }
        }
    }
    (result, positions)
}

fn verify(file: &File, label: &str, languages: [&str; 2], print_bytes: bool) {
    let syntax = syntax::Syntax::new(file, &component::highlighter::HighlightTheme);
    let captured = CAPTURE.with_borrow_mut(std::mem::take);
    assert_eq!(captured.len(), 2);
    for (index, (side, language)) in captured.into_iter().zip(languages).enumerate() {
        let old = index == 0;
        let (want_source, want_ranges) = expected(file, old);
        assert_eq!(
            side.source.as_bytes(),
            want_source.as_bytes(),
            "{label}/{old}"
        );
        assert_eq!(side.ranges, want_ranges, "{label}/{old}");
        assert_eq!(side.language, language, "{label}/{old}");
        let oracle = modeled_styles(&want_source);
        let mut trace = std::collections::hash_map::DefaultHasher::new();
        let mut render_spans = 0;
        let mut cross_row = 0;
        if print_bytes {
            println!(
                "INPUT {label}/{old}: {:?}; ranges={want_ranges:?}",
                side.source
            );
        }
        want_source.hash(&mut trace);
        want_ranges.hash(&mut trace);
        for (row, range) in want_ranges.into_iter().enumerate() {
            let shape = range
                .map(|r| {
                    let mut local = Vec::new();
                    for (style_range, style) in &oracle {
                        let a = style_range.start.max(r.start);
                        let b = style_range.end.min(r.end);
                        if a < b {
                            cross_row +=
                                usize::from(style_range.start < r.start || style_range.end > r.end);
                            assert!(
                                side.source.is_char_boundary(a) && side.source.is_char_boundary(b)
                            );
                            local.push((a - r.start..b - r.start, *style));
                        }
                    }
                    local
                })
                .unwrap_or_default();
            assert_eq!(&shape, syntax.line(row, old), "{label}/{old}/{row}");
            render_spans += shape.len();
            shape.hash(&mut trace);
        }
        println!(
            "SIDE {label}/{old}: lang={language} bytes={} rows={} spans={render_spans} cross_row={cross_row} oracle={:016x}",
            side.source.len(),
            file.lines.len(),
            trace.finish()
        );
        eprintln!(
            "WORK side {label}/{old}: {} {}",
            side.work.requests, side.work.bytes
        );
    }
}

fn fixture() -> Vec<File> {
    let raw = concat!(
        "diff --git a/old.rs b/new.py\r\n",
        "rename from old.rs\r\n",
        "rename to new.py\r\n",
        "--- a/old.rs\r\n",
        "+++ b/new.py\r\n",
        "@@ -1,4 +1,5 @@ header\r\n",
        " \tдо\t\t🚀\t\r\n",
        "-\tlet before = \"мир\";\t\r\n",
        "+\tlet after = \"état\";\t\r\n",
        "+\t\t\r\n",
        " \r\n",
        " обычная строка\r\n",
        "@@ -10 +11 @@\r\n",
        "-без перевода\r\n",
        "\\ No newline at end of file\r\n",
        "+new without LF",
    );
    diff::parse(
        raw,
        &[FileInfo {
            path: "metadata.md".into(),
            status: "binary".into(),
            message: Some("not present".into()),
        }],
    )
}

fn many(name: &str, style: &str) -> File {
    let mut patch =
        format!("diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n@@ -1,360 +1,360 @@\n");
    for i in 0..240 {
        let row = match style {
            "spaces" => format!("    let abc_{i} = \"данные\";"),
            "sparse-tabs" => format!("\tlet abc_{i} = \"данные\";\t// 🌈"),
            "dense-tabs" => "\t".repeat(25 + i % 13),
            _ => unreachable!(),
        };
        writeln!(patch, " {row}").unwrap();
        if i % 2 == 0 {
            writeln!(patch, "-{row} // before\n+{row} // after").unwrap();
        }
    }
    let mut files = diff::parse(&patch, &[]);
    assert_eq!(files.len(), 1);
    let file = files.pop().unwrap();
    assert_eq!(
        file.lines
            .iter()
            .filter(|row| row.kind == Kind::Context)
            .count(),
        240
    );
    assert_eq!((file.added, file.removed), (120, 120));
    file
}

fn isolated(label: &str, text: &str) {
    // Prepare the destination and the oracle entirely outside the count.
    let expanded = text.replace('\t', "    ");
    let mut dest = String::with_capacity(2 + expanded.len());
    dest.push_str("a:");
    count::start();
    syntax::isolated_append(&mut dest, text);
    let work = count::stop();
    assert_eq!(dest, "a:".to_owned() + &expanded);
    println!("APPEND {label}: {} {}", text.len(), expanded.len());
    eprintln!("WORK append {label}: {} {}", work.requests, work.bytes);
}

fn main() {
    eprintln!("ARM {}", env!("R99_DIFF_ARM"));
    for (label, text) in [
        ("blank", ""),
        ("no-tabs", "данные"),
        ("sparse-tabs", "\t🚀\t\té\t"),
        ("dense-tabs", "\t\t\t\t\t\t\t\t\t\t\t\t"),
        ("non-tabs", "🚀\u{00a0}\u{000b}\r\n"),
    ] {
        isolated(label, text);
    }
    let files = fixture();
    assert_eq!(files.len(), 2);
    assert_eq!(files[0].old_path.as_deref(), Some("old.rs"));
    assert_eq!(&files[0].path, "new.py");
    assert_eq!(
        files[0]
            .lines
            .iter()
            .filter(|row| row.kind == Kind::Hunk)
            .count(),
        2
    );
    assert!(files[0].lines.iter().any(|row| row.no_newline));
    assert!(
        files[0]
            .lines
            .iter()
            .any(|row| row.kind == Kind::Context && row.text.is_empty())
    );
    assert!(files[1].lines.iter().all(|row| row.kind == Kind::Note));
    verify(&files[0], "renamed-crlf", ["rust", "python"], true);
    verify(&files[1], "metadata-only", ["markdown", "markdown"], true);
    for style in ["spaces", "sparse-tabs", "dense-tabs"] {
        verify(&many("normal.rs", style), style, ["rust", "rust"], false);
    }
    verify(&File::default(), "empty-file", ["text", "text"], true);
    // Direct model row tests protect the eligible empty range and raw
    // non-LF text handling independently of the parser's normalizations.
    let file = File {
        lines: vec![
            Line {
                kind: Kind::Context,
                text: String::new(),
                old: None,
                new: None,
                no_newline: false,
            },
            Line {
                kind: Kind::Added,
                text: "\tend\t".into(),
                old: None,
                new: None,
                no_newline: true,
            },
        ],
        ..File::default()
    };
    verify(&file, "direct-blank-and-end", ["text", "text"], true);
}
