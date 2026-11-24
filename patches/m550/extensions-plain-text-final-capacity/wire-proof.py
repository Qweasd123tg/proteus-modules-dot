"""Differential real protocol-v4 Markdown/text/plain lines, no server or network."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

binary, output = (Path(p).resolve() for p in sys.argv[1:])
synth = "/synthetic/plain-footers"
plain = "  Привет 🦀 \u2028\r\n x@y.example \0|  ".replace("\\0","\0")*32768
late = plain + '<&"Ж'
last_link = " leading <b> http://example.invalid/path?a=1&b=2"
escaped = ' <> "& </div> \r\n 🦀'
nested_like = r'[scope](https://example.invalid/a) &amp; What?' + "\r\n"
plain_again = 'Changed </div> plain Ж🦀'
inputs = [plain,late,last_link,escaped,nested_like,"",plain_again]
view = "same view"
hello = {"type":"hello","protocol":4,"features":["surfaces.content.v1","widgets.rich_text.v1"]}
def message(i, text, context="left"):
    return {"type":"render","session_dir":synth+context,"view":view,
            "context":context,"surface":"content",
            "content":{"source":text,"source_revision":i,"language":"text/plain"}}
close={"type":"close","context":"left","session_dir":synth+"left","view":view}
frames=[hello,*[message(i,text) for i,text in enumerate(inputs[:-1],1)],close,message(7,inputs[-1],"right")]
encoded=b"".join((json.dumps(x,ensure_ascii=False)+"\n").encode() for x in frames)
run=subprocess.run([binary],input=encoded,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=40)
assert not run.stderr, run.stderr[:500]
rows=[json.loads(line) for line in run.stdout.split(b"\n") if line]
assert [(row["type"],row["source_revision"]) for row in rows] == [("view",n) for n in range(1,8)]
open_div='<div style="white-space: pre-wrap">'
ends='</div>'
def wrap(s): return open_div+s+ends
bodies=[plain,plain+'&lt;&amp;&quot;Ж',
        ' leading &lt;b&gt; <a href="http://example.invalid/path?a=1&amp;b=2">http://example.invalid/path?a=1&amp;b=2</a>',
        ' &lt;&gt; &quot;&amp; &lt;/div&gt; \r\n 🦀',
        '[scope](<a href="https://example.invalid/a">https://example.invalid/a</a>) &amp;amp; What?\r\n',
        "",'Changed &lt;/div&gt; plain Ж🦀']
for row, body in zip(rows,bodies,strict=True):
    assert row["root"]=={"type":"rich_text","id":view,"html":wrap(body)}, repr(row)[:500]
assert rows[-1]["session_dir"]==synth+"right"
output.write_bytes(run.stdout)
print(len(rows),len(run.stdout),sha256(run.stdout).hexdigest())
