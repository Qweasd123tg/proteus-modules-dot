"""Lift the production fold decision and formatters without a GPUI runtime."""
import re


def row_parts(source):
    def once(marker):
        assert source.count(marker) == 1, marker
        return source.index(marker)

    start = once("        let build = |text| clipped_surface(build(text), self.clip, cx);\n")
    start = source.index("\n", start) + 1
    gui = source.index("        let theme = cx.theme();\n", start)
    label = source.index("        let label = if ", gui)
    post = source.index("\n        v_flex()\n", label) + 1
    assert start < gui < label < post
    assert source[gui:label] == (
        "        let theme = cx.theme();\n"
        "        let chat = self.chat.clone();\n"
        "        let copy_chat = self.chat.clone();\n"
        "        let key = self.key;\n"
    )
    return (source[:start], source[start:gui], source[gui:label],
            source[label:post], source[post:])


def row_module(source, name):
    _, decision, _, label, _ = row_parts(source)
    constants = "\n".join(
        re.findall(r"^const (?:PEEK|FULL)_(?:LINES|CHARS): usize = [\d_]+;", source, re.M)
    )
    assert constants.splitlines() == [
        "const PEEK_LINES: usize = 12;", "const PEEK_CHARS: usize = 2_000;",
        "const FULL_LINES: usize = 400;", "const FULL_CHARS: usize = 40_000;",
    ]
    output = """
        Projection::Long {
            full,
            preview,
            label,
            clipped: format::clip_block(text, FULL_LINES, FULL_CHARS),
        }
"""
    exact_body = decision + label
    instrumented = exact_body
    for obj, counter in (("text", "source_lines"), ("preview", "preview_lines")):
        needle = f"{obj}.lines()"
        assert instrumented.count(needle) in (1, 2), needle
        instrumented = instrumented.replace(
            needle, f"{needle}.inspect(|_| {counter}.set({counter}.get() + 1))",
        )

    def method(method_name, body, count_params):
        return (
            f"    pub fn {method_name}(&self, part: usize, text: &str"
            f"{count_params}) -> Projection {{\n"
            "        let build = Projection::Short;\n" + body + output + "    }\n"
        )

    return (
        f"mod {name} {{\n"
        "use super::{Projection, format};\n"
        "use std::cell::Cell;\n"
        + constants + "\n"
        "pub struct Fold { pub full: [bool; 2] }\n"
        "impl Fold {\n"
        + method("block", exact_body, "")
        + method(
            "counted", instrumented,
            ", source_lines: &Cell<usize>, preview_lines: &Cell<usize>",
        )
        + "}\n}\n"
    )


def lift(stock, candidate, formatter, cases, target):
    a, b = row_parts(stock), row_parts(candidate)
    assert (a[0], a[2], a[4]) == (b[0], b[2], b[4]), "GPUI prefix/suffix changed"
    assert "preview_reveal(" in a[4] and "chat.copy_tool_block(key, part, cx)" in a[4]
    assert "|| build(format::clip_block(text, FULL_LINES, FULL_CHARS))" in a[4]
    start = formatter.index("pub fn peek_block(")
    end = formatter.index("const PREVIEW_LINES:", start)
    formatters = formatter[start:end]
    assert formatters.count("pub fn ") == 2 and "pub fn clip_block(" in formatters
    target.write_text(
        "mod format {\n" + formatters + "}\n"
        + row_module(stock, "stock") + row_module(candidate, "candidate") + cases,
        encoding="utf-8",
    )
