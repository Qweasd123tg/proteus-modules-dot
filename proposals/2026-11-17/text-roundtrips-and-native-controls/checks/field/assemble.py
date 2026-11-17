"""Compile the pinned input reconciliation decision without creating a real UI."""
from pathlib import Path
import sys

def between(source, start, end):
    i = source.index(start)
    return source[i:source.index(end, i + len(start))]

root = Path(sys.argv[1])
fields = (root / "src/ui/extensions/declarative/fields.rs").read_text()
render = (root / "src/ui/extensions/declarative/render.rs").read_text()
widget = (root / "src/declarative/widget.rs").read_text()
text = Path(__file__).with_name("fixture.rs").read_text()
decision = between(fields, "            Node::Input {\n                id,\n                value,", "            Node::Code")
text = text.replace("//IMPL_TEXT", between(fields, "pub(super) enum Text {", "/// Embedded prose").replace("pub(super)", "pub(crate)"))
text = text.replace("//INPUT_ARM", decision)

# Retain the actual discriminant test, replacing the two graphical outcomes with labels.
both = between(render, "            Node::Input {\n                id,\n                search: true", "            Node::Svg")
arm = both[:both.index("            Node::Input {\n                id, flush")]
match = between(arm, "match &input.state {", "                })")
assert "super::fields::Text::Line(input) => Some(" in match
assert ".unwrap_or_else(|| div().into_any_element())" in arm
assert "if *lines != 1 =>" in widget and "if !(1..=40).contains(lines)" in widget
decision = (match[:match.index("super::fields::Text::Line(input)")]
            + 'Text::Line(_) => Some("Search"),\n'
            + match[match.index("super::fields::Text::Area(_) => None"):].replace("super::fields::Text::Area", "Text::Area")
            + "}")
i = text.index("fn present(")
j = text.index("fn main()", i)
text = text[:i] + """
fn present(v: &DeclarativeView, search: bool, cx: &App) -> (&'static str, usize, u64) {
    let input = &v.fields.inputs["filter"];
    let (kind, rows, id) = match &input.state {
        Text::Line(s) => ("Line", 1, s.read(cx).id),
        Text::Area(s) => ("Area", s.read(cx).row_min, s.read(cx).id),
    };
    let kind = if search { (""" + decision + """).unwrap_or("Empty") } else { kind };
    (kind, rows, id)
}
""" + text[j:]
print(text)
