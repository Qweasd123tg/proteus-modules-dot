"""Instrument actual HTML/Markdown parser entry points in a disposable gpui-base."""
import sys
from pathlib import Path

target = Path(sys.argv[1]) / "src/text"
for i, name in enumerate(("html", "markdown")):
    path = target / "format" / (name + ".rs")
    code = path.read_text()
    mark = "pub(crate) fn parse(source: &str, cx: &mut NodeContext) -> Result<ParsedDocument, SharedString> {"
    assert code.count(mark) == 1 and "r5_tick" not in code
    path.write_text(code.replace(mark, mark + f"\n    crate::text::state::r5_tick({i}, source.len());"))
state = target / "state.rs"
assert "static R5_COUNTS" not in state.read_text()
with state.open("a") as f:
    f.write("\n" + Path(__file__).with_name("observe.rs").read_text())
