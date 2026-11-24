"""Synthetic protocol trace through the actual Mermaid binary and vendored Node worker."""
import hashlib
import os
import shutil
import tempfile
import json
from pathlib import Path
import subprocess
import sys

binary, cwd, output = [Path(s).resolve() for s in sys.argv[1:]]
s1, s2 = "/synthetic/one", "/synthetic/two"
left = {"context": "left", "session_dir": s1, "view": "v-a"}
right = {"context": "right", "session_dir": s2, "view": "v-b"}
theme = {
    "foreground":"#dddddd","background":"#181818","accent":"#99aaff",
    "muted":"#999999","border":"#555555","danger":"#ff9999",
    "surface":"#222222","surface_alt":"#333333",
    "font_family":"sans-serif","font_family_mono":"monospace"}

changed_theme = {**theme, "background": "#252525", "foreground": "#aabbcc"}
source = 'flowchart LR\r\n A["Привет; &amp; 🦀"]-->B[Мир]'
frames = [{"type":"hello","protocol":4,"features":["surfaces.content.v1","widgets.svg.v1"]}]
def draw(ctx, rev, text=source, shade=theme):
    frames.append(dict(ctx, type="render",surface="content",
                       content=dict(language="mermaid",source=text,source_revision=rev,
                                    context={"theme":shade})))
def close(ctx):
    frames.append(dict(ctx, type="close"))
draw(left,1)
draw(right,1)                                # share first result across sessions
draw(right,2,shade=changed_theme)             # theme-only miss
draw(left,2)                                 # original entry stays with first owner
draw(right,3,text="unsupported Привет")      # Node-side parse failure / replacement
draw(right,4,shade=changed_theme)             # success after failed worker
draw(right,5,text="x"*50001)                   # before-worker validation
draw(right,6,shade=dict(theme, unused="x"*524288))  # before-worker wire-byte bound
close(left)
close(right)
draw(right,7)                                # first request after final close
encoded=b"".join((json.dumps(i,ensure_ascii=False)+"\n").encode() for i in frames)
# Observe real worker child ownership without needing /proc/PID/task/TID/children.
# No transformation of args, cwd, stdin or stdout; the shell execs the real Node.
node = shutil.which("node")
assert node and Path(node).is_file()
with tempfile.TemporaryDirectory(prefix="proteus-mermaid-synthetic-path-") as directory:
    path=Path(directory)
    shim=path/"node"
    shim.write_text('#!/bin/sh\nprintf "%s\\n" "$$" >> "$MERMAID_FIXTURE_PIDS"\nexec "$MERMAID_FIXTURE_NODE" "$@"\n')
    shim.chmod(0o755)
    pids_path=path/"worker-pids"
    environ={**os.environ,"PATH":directory+os.pathsep+os.environ["PATH"],
             "MERMAID_FIXTURE_PIDS":str(pids_path),"MERMAID_FIXTURE_NODE":node}
    proc=subprocess.run([binary], input=encoded, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=environ, check=True, timeout=30)
    pids=list(map(int,pids_path.read_text().splitlines()))
    # Lazy creation across both first views, restart after parser error, restart after
    # last close; all three workers have been reaped by the parent's EOF.
    assert len(pids)==len(set(pids))==3, pids
    for pid in pids:
        try:
            os.kill(pid,0)
        except ProcessLookupError:
            continue
        raise AssertionError(f"worker {pid} survives parent EOF")
assert not proc.stderr, proc.stderr[:1000]
replies=[json.loads(line) for line in proc.stdout.splitlines()]
assert [(x["view"],x["source_revision"],x["type"]) for x in replies] == [
    ("v-a",1,"view"),("v-b",1,"view"),("v-b",2,"view"),("v-a",2,"view"),
    ("v-b",3,"content_error"),("v-b",4,"view"),("v-b",5,"content_error"),
    ("v-b",6,"content_error"),("v-b",7,"view")], str(replies)[:2500]
a,b,c,d,e,f,g,h,i = replies
for x in [a,b,c,d,f,i]:
    assert x["root"]["type"]=="svg"
    assert "Привет" in x["root"]["source"]
    assert 1 <= x["root"]["height"] <= 4096
    assert 1 <= x["root"]["width"] <= 4096
assert a["root"]==b["root"]==d["root"]==i["root"]
assert c["root"]==f["root"] and a["root"]!=c["root"]
assert e["error"] and "50,000 bytes" in g["error"] and "request is too large" in h["error"]
assert a["session_dir"] == s1 and i["session_dir"] == s2
output.write_bytes(proc.stdout)
print(len(proc.stdout), hashlib.sha256(proc.stdout).hexdigest())
