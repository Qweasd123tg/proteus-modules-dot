#!/usr/bin/env python3
"""Synthetic content-only protocol. No server address or external state."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess as sp

PACKAGE = Path("packages/markdown-render")
TITLE = "The calculation below uses synthetic coefficients only. "
SIMPLE = "w_{1}=\\alpha^2+4β"
SPECIAL = "x<y &amp; z>β+é"
FORMULAS = [
    "u_1=α+β", "R_{ij}=x_i+y_j", SPECIAL, "s_n=\\frac{n(n+1)}{2}",
    "t=λ+2é", "P(X>c)=p", "x_{1}<x_{2}", "v=δ^2",
    "A_{ij}=a_i+b_j", "r=\\sqrt{x^2+y^2}", "Q=θ+ϕ", "p=ρ & z=η",
]
DENSE = "λ" + "<>&" * 512 + "β"
BIG = "λ" * (16 * 1024)


def esc(raw):
    return raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def math_note(formulas):
    return " ".join(f"{TITLE}Term {i + 1} is ${body}$; this is its documented value."
                    for i, body in enumerate(formulas))


def raw_frame(payload):
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def inputs(features):
    batch = []
    def add(label, rev, source, languages, view="article", language="text/markdown"):
        batch.append((label, {"type": "render", "context": "fixture", "view": view,
                              "surface": "content", "content": {"language": language, "source": source,
                              "source_revision": rev, "context": {"languages": languages}}}))
    def close(view):
        batch.append((None, {"type": "close", "view": view}))
    batch.append((None, {"type": "hello", "protocol": 4, "features": features}))
    add("single", 1, math_note([SIMPLE]), ["latex"])
    add("one-special", 2, math_note([SPECIAL]), ["latex"])
    add("ordinary", 3, math_note(FORMULAS), ["latex", "tex"])
    append = math_note(FORMULAS) + " Tail \\$outside\\$ and $ζ<μ$."
    add("tail-edit", 4, append, ["latex", "tex"])
    add("same-tail", 5, append, ["latex", "tex"])
    add("reordered", 6, append, ["tex", "latex"])
    add("tex-only", 7, append, ["tex"])
    add("disabled", 8, append, ["mermaid"])
    add("cold", 19, append, ["tex"], "other")
    close("article")
    add("reopen", 1, append, ["tex"])
    add("footnotes", 2, "[^note]: Footnote $y<z$\n\n[^unused]: Hidden $u&v$\n\nBody $a&b$ and note[^note].", ["latex"])
    add("policy", 3,
        "<mark>authored raw tag</mark>\n\n**$x<y &amp; z>β$** and `$literal$`. "
        "Price $100 and \\$x=2\\$ here. ![literal $alt$](https://example.invalid/y.png) "
        "[link](https://example.invalid/a?q=1&b=2)",
        ["latex"])
    add("dense", 4, "$" + DENSE + "$", ["latex"])
    add("bounded", 5, "$" + BIG + "$", ["latex"])
    add("oversize", 6, "$" + BIG + "x$", ["latex"])
    opened = "Before $a+b$.\n\n~~~mermaid\r\nА --> Б"
    finished = opened + "\r\n~~~\r\n\n~~~RuSt\r\nlet x = 'λ';\r\n~~~\r\n\n"
    add("fence-open", 7, opened, ["mermaid", "latex"])
    add("fence-closed", 8, finished, ["mermaid", "latex"])
    add("fence-tail", 9, finished + "One more $z<l$.", ["mermaid", "latex"])
    add("plain", 10, 'literal <mark> & "quotes" and $x$', ["latex"], language="text/plain")
    batch.append(("preview", {"type": "render", "context": "fixture", "view": "preview",
                              "surface": "preview"}))
    for view in ("article", "other", "preview"):
        close(view)
    return batch


def leaves(node):
    return [node, *(item for child in node.get("children", []) for item in leaves(child))]


def content(root):
    nodes = leaves(root)
    slots = [slot for node in nodes for slot in node.get("inlines", [])]
    html = "".join(node.get("html", "") for node in nodes)
    return slots, html


def replay(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]
    batch = inputs(features)
    data = b"".join(raw_frame(msg) for _, msg in batch)
    proc = sp.run([exe], cwd=src / PACKAGE, env=env, input=data,
                  capture_output=True, check=True, timeout=15)
    assert not proc.stderr, proc.stderr
    frames = [json.loads(row) for row in proc.stdout.splitlines()]
    expected = [(label, msg) for label, msg in batch if label is not None]
    roots = {}
    for frame, (label, request) in zip(frames, expected, strict=True):
        assert frame["type"] == "view" and frame["view"] == request["view"], (label, frame)
        assert frame.get("source_revision") == request.get("content", {}).get("source_revision"), label
        roots[label] = frame["root"]

    for label, bodies, lang in [
        ("single", [SIMPLE], "latex"), ("one-special", [SPECIAL], "latex"),
        ("ordinary", FORMULAS, "latex"), ("tail-edit", FORMULAS + ["ζ<μ"], "latex"),
        ("reordered", FORMULAS + ["ζ<μ"], "latex"),
        ("tex-only", FORMULAS + ["ζ<μ"], "tex"), ("dense", [DENSE], "latex"),
        ("bounded", [BIG], "latex"), ("oversize", [], "latex"),
    ]:
        slots, html = content(roots[label])
        assert [slot["source"] for slot in slots] == bodies, (label, len(slots))
        assert all(slot["language"] == lang for slot in slots), label
        for slot, body in zip(slots, bodies, strict=True):
            assert f'<span data-content="{slot["id"]}">${esc(body)}$</span>' in html, label
    assert roots["tail-edit"] == roots["same-tail"]
    assert roots["tex-only"] == roots["cold"] == roots["reopen"]
    assert content(roots["disabled"])[0] == []
    slots, html = content(roots["footnotes"])
    assert [(s["id"], s["source"]) for s in slots] == [("inline-0", "y<z"), ("inline-2", "a&b")]
    assert html.index('data-content="inline-2"') < html.index('data-content="inline-0"')
    assert 'data-content="inline-1"' not in html
    slots, html = content(roots["policy"])
    assert [s["source"] for s in slots] == ["x<y &amp; z>β"]
    assert "<mark>" not in html and "<code>$literal$</code>" in html and "$100" in html
    assert 'href="https://example.invalid/a?q=1&amp;b=2"' in html
    assert 'alt="literal $alt$"' in html
    assert content(roots["plain"]) == (
        [], '<div style="white-space: pre-wrap">literal &lt;mark&gt; &amp; &quot;quotes&quot; and $x$</div>'
    )
    initial = leaves(roots["fence-open"])
    completed = leaves(roots["fence-closed"])
    assert any(n.get("type") == "code" and n.get("text") == "А --> Б" for n in initial)
    assert any(n.get("type") == "content" and n.get("source") == "А --> Б\r\n" for n in completed)
    assert any(n.get("type") == "code" and n.get("text") == "let x = 'λ';\r\n" for n in completed)
    assert [s["source"] for s in content(roots["fence-tail"])[0]] == ["a+b", "z<l"]
    assert any(n.get("type") == "code" for n in leaves(roots["preview"]))
    assert content(roots["preview"])[0] == []
    return data, proc.stdout, proc.stderr
