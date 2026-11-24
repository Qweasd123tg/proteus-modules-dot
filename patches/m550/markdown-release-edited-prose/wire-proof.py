"""Real native Markdown content route with repeated large single- and multi-segment edits."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

binary, output = (Path(p).resolve() for p in sys.argv[1:])
session = "/synthetic/owned-segment"
header = "Большое сообщение 🦀\r\n\r\n"
body = "ab Я🦀 plain ".upper()*48000
pure=header+body
fenced="Перед оградой 🧪\r\n\r\n```mermaid\r\nflowchart LR\r\nA-->B\r\n```\r\n\r\n"
tail="Стриминг \r\n\r\n"+body
source=fenced+tail
fixtures=[
    (pure,["mermaid"],"left"),
    (pure+" ещё",["mermaid"],"left"),
    (pure+" ещё",["mermaid"],"left"),
    (source,["mermaid"],"left"),
    (source+" дописали **ссылку**",["mermaid"],"left"),
    (source.replace("A-->B","A-->C"),["mermaid"],"left"),
    (source.replace("A-->B","A-->C")+" [вперёд][late]\n\n[late]: https://example.invalid/late",["mermaid"],"left"),
    (source,[],"left"),
    ("Новое окно",["mermaid"],"right"),
]
hello={"type":"hello","protocol":4,"features":["surfaces.content.v1","widgets.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1","widgets.code_embedded.v1"]}
def render(n,text,langs,context):
    return {"type":"render","view":"fixture","context":context,"session_dir":session+context,
            "surface":"content","content":{"source":text,"language":"text/markdown","source_revision":n,
                                          "context":{"languages":langs}}}
packets=[hello,*[render(n,*f) for n,f in enumerate(fixtures[:-1],1)],
         {"type":"close","view":"fixture","context":"left","session_dir":session+"left"},render(9,*fixtures[-1])]
payload=b"".join((json.dumps(p,ensure_ascii=False)+"\n").encode() for p in packets)
proc=subprocess.run([binary],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=50)
assert not proc.stderr, proc.stderr[:500]
rows=[json.loads(line) for line in proc.stdout.split(b"\n") if line]
assert [(r["type"],r["source_revision"]) for r in rows]==[("view",i) for i in range(1,10)]
def children(n):
    return rows[n-1]["root"]["children"]
def text(n):
    return "".join(v.get("html","") for v in children(n))
for n in range(1,9):
    assert body.rstrip() in text(n)
assert rows[1]["root"] == rows[2]["root"]
assert "ещё" in text(2) and "ещё" not in text(1)
assert children(4)[1]==children(5)[1] and children(4)[1]["type"]=="content"
assert "дописали <strong>ссылку</strong>" in text(5)
assert children(6)[1]["source"]=="flowchart LR\r\nA-->C\r\n"
assert 'href="https://example.invalid/late"' in text(7)
assert children(8)[1]["type"]=="code" and children(8)[1]["text"]=="flowchart LR\r\nA-->B\r\n"
assert rows[8]["session_dir"]==session+"right" and len(children(9))==1 and "Новое окно" in text(9)
output.write_bytes(proc.stdout)
print(len(rows),len(proc.stdout),sha256(proc.stdout).hexdigest())
