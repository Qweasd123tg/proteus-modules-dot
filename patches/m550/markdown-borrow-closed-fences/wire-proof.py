"""Actual native Markdown binary: preserve source bytes and fallback across revisions."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

binary, output = (Path(p).resolve() for p in sys.argv[1:])
session = "/synthetic/fences"
raw_code = ('Я🦀 "ASCII" &<\0\t '*36_000)+"\r\n"
code_fence = "До [цель][late]\r\n\r\n```MeRmAiD\r\n"+raw_code+"```\r\n"
head = code_fence+"\r\nхвост"
flow_math = "$$\r\n\\frac{🦀}{Я}\r\n$$\r\n"
literal = "~~~MarkDown\r\n```mermaid\r\nА-->Б\r\n```\r\n~~~\r\n"
fixtures = [
    (head, ["mermaid"], "left"),
    (head+" [цель][late]\r\n\r\n[late]: https://example.invalid/🦀\r\n",["mermaid"],"left"),
    (head, [], "left"),
    (literal, ["mermaid","markdown"], "left"),
    (flow_math, ["tex"], "left"),
    ("```mermaid\r\nначало 🦀\r\n``` продолжение",["mermaid"],"left"),
    ("$$\r\nнезакрытая формула",["tex"],"left"),
    ("> ```mermaid\n> А-->Б\n> ```",["mermaid"],"left"),
    ("```mermaid\nА-->Б\n```",["mermaid"],"right"),
]
hello={"type":"hello","protocol":4,"features":["surfaces.content.v1","widgets.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1","widgets.code_embedded.v1"]}
def render(n,text,languages,context):
    return {"type":"render","view":"card","context":context,"session_dir":session+context,
            "surface":"content","content":{"source":text,"language":"text/markdown","source_revision":n,
                                          "context":{"languages":languages}}}
frames=[hello,*[render(n,*f) for n,f in enumerate(fixtures[:-1],1)],
        {"type":"close","view":"card","context":"left","session_dir":session+"left"},render(9,*fixtures[-1])]
payload=b"".join((json.dumps(f,ensure_ascii=False)+"\n").encode() for f in frames)
run=subprocess.run([binary],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=40)
assert not run.stderr, run.stderr[:500]
rows=[json.loads(line) for line in run.stdout.split(b"\n") if line]
assert [(r["type"],r["source_revision"]) for r in rows]==[("view",n) for n in range(1,10)]
def child(n):
    return next(c for c in rows[n-1]["root"]["children"] if c.get("id")=="code-0")
assert all(child(n)["type"]=="content" and child(n)["source"]==raw_code for n in (1,2))
assert child(3)["type"]=="code" and child(3)["text"]==raw_code
assert any("example.invalid" in c.get("html","") for c in rows[1]["root"]["children"])
assert child(4)["type"]=="code" and child(4)["text"]=="```mermaid\r\nА-->Б\r\n```\r\n"
assert child(5)["type"]=="content" and child(5)["language"]=="tex" and child(5)["source"]=="\\frac{🦀}{Я}\r\n"
assert child(6)["type"]=="code" and "продолжение" in child(6)["text"]
assert all(all(c["type"]!="content" for c in rows[n-1]["root"]["children"]) for n in (7,8))
assert child(9)["type"]=="content" and child(9)["source"]=="А-->Б\n" and rows[8]["session_dir"]==session+"right"
output.write_bytes(run.stdout)
print(len(rows),len(run.stdout),sha256(run.stdout).hexdigest())
