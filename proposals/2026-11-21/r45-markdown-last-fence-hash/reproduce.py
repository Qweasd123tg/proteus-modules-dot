#!/usr/bin/env python3
"""Replay locked package tests, unmodified process output/timing and separate hash counts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from statistics import median
import subprocess as sp
import sys
import tempfile
from time import perf_counter_ns

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-markdown-render"
PATCH = HERE / "source.patch"
REPO = Path(sys.argv[1]).resolve()
HELLO = {"type":"hello","protocol":4,"workspace":"/fixture","features":[
    "surfaces.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1",
    "widgets.content.v1","widgets.code_embedded.v1"]}
LANGS = ["mermaid","latex","md"]
def wire(sources):
    rows = [HELLO]
    for rev, (text, languages) in enumerate(sources, start=1):
        rows.append({"type":"render","context":"test","surface":"content","view":"view",
            "session_dir":"/fixture","content":{"language":"text/markdown","source":text,
            "source_revision":rev,"context":{"languages":languages}}})
    return b"".join((json.dumps(row,ensure_ascii=False,separators=(",",":"))+"\n").encode() for row in rows)
def compare(root):
    block = "```rust\n" + "x"*256 + "\n```\n"
    bsize = len(block.encode())
    doc = "[url]: /docs\n\n```mermaid\nα-->β\n```\n\n$$\ny\n$$\r\n"
    edits = [doc+r for r in ["\n[go][url]","\n[go][url]\n\n~~~md\nz\n~~~","\n[go][url]\n\n~~~md\nz\n~~~\n"]]
    edits += [edits[-1].replace("α","γ"), edits[-1].replace("α","γ")]
    cases = [(f"cold-{n}",[(block*n if n else "ordinary prose",LANGS)],n)
             for n in (0,1,32,256,1024)]
    cases += [("append-32-to-256",[(block*32,LANGS),(block*256,LANGS)],None),
              ("unicode-edits-policy",[(s,LANGS if i<4 else []) for i,s in enumerate(edits)],None)]
    for name, sources, n in cases:
        payload = wire(sources)
        raws = {}
        for arm in ("stock","candidate"):
            binary = root / arm
            result = sp.run([binary], input=payload, capture_output=True, check=True)
            out = result.stdout
            rows = [json.loads(s) for s in out.splitlines()]
            assert [r.get("source_revision") for r in rows] == list(range(1,len(sources)+1)), name
            assert all(r["type"]=="view" and r["root"]["type"]=="stack" for r in rows), name
            if n:
                assert len(rows[0]["root"]["children"])==n, name
            raws[arm] = out
            counted = sp.run([root/(arm+"-count")],input=payload,capture_output=True,check=True)
            assert counted.stdout==out, name
            sizes = [int(line.split(b":")[1]) for line in counted.stderr.splitlines() if line.startswith(b"HASH:")]
            if n is not None:
                ends = [bsize*i-1 for i in range(1,n+1)]
                assert sizes==(ends if arm=="stock" else ends[-1:]), (name,arm)
            elif name=="append-32-to-256":
                ends = [bsize*i-1 for i in range(1,257)]
                expected = ends[:32]+[ends[31]]+ends[32:] if arm=="stock" else [ends[31],ends[31],ends[-1]]
                assert sizes==expected, (name,arm)
            print(name, arm, "calls",len(sizes),"input_bytes_hashed",sum(sizes),flush=True)
        assert raws["stock"]==raws["candidate"], name
        print(name,"verified_wire_bytes",len(out),"sha256",hashlib.sha256(out).hexdigest())
        if n is None:
            continue
        # Timed binaries have no counter or tracing. The input is prepared outside this timer.
        timings = {"stock":[],"candidate":[]}
        for i in range(7):
            for arm in (("stock","candidate") if i%2==0 else ("candidate","stock")):
                start = perf_counter_ns()
                output = sp.run([root/arm],input=payload,stdout=sp.PIPE,stderr=sp.PIPE,check=True).stdout
                timings[arm].append((perf_counter_ns()-start)//1000)
                assert output==out
        print(name,"source_bytes",len(sources[0][0].encode()),"process_wall_us",
              {k:{"median":median(v),"raw":v} for k,v in timings.items()},flush=True)

def recovery(root):
    # Fault injection only in instrumented executables. This is not a parser bug or source fixture in production.
    fence = "```rust\nx\n```\n"
    base = fence
    good = base+fence+"\nrecovered\n\n"+fence
    isolated = sp.check_output([root/"candidate"],input=wire([(good,LANGS)]))
    expected = json.loads(isolated)["root"]
    for fault in ("ERR","PANIC"):
        bad = good.replace("recovered","FAULT_"+fault)
        frame = wire([(base,LANGS),(bad,LANGS),(good,LANGS)])
        for arm in ("stock","candidate"):
            result = sp.run([root/(arm+"-count")],input=frame,capture_output=True,check=True)
            rows = [json.loads(x) for x in result.stdout.splitlines()]
            assert len(rows)==3 and rows[0]["type"]=="view", (arm,fault)
            assert [r["source_revision"] for r in rows]==[1,2,3]
            assert rows[1]["type"]=="content_error" and rows[1]["error"]==fault, (arm,fault,rows)
            if arm=="candidate":
                assert rows[2]["type"]=="view" and rows[2]["root"]==expected, (arm,fault)
            else:
                assert rows[2]["type"]=="content_error", (arm,fault)
            print("injected",fault,arm,"revision2",rows[1]["type"],"revision3",rows[2]["type"],
                  "cold_equal",rows[2].get("root")==expected,flush=True)

with tempfile.TemporaryDirectory(prefix="r45-fence-hash-") as tmp:
    root = Path(tmp)
    src = root/"src"
    sp.run(["git","clone","--quiet","--shared","--no-checkout",REPO,src],check=True)
    def cmd(*args):
        sp.run(args,cwd=src,env=env,check=True)
    env = dict(os.environ,CARGO_TARGET_DIR=str(root/"target"),CARGO_INCREMENTAL="0",TZ="UTC")
    cmd("git","checkout","-q","--detach",BASE)
    cmd("git","apply","--index","--check",PATCH)
    for arm in ("stock","candidate"):
        if arm=="candidate":
            cmd("git","apply","--whitespace=error",PATCH)
            cmd("git","diff","--check")
            cmd("git","apply","--reverse","--check",PATCH)
            cmd("cargo","fmt","--check","-p",PKG)
        cmd("cargo","test","--locked","--release","-p",PKG)
        exe = root/"target/release/markdown-render"
        shutil.copy2(exe,root/arm)
        path=src/"packages/markdown-render/src/render.rs"
        original=path.read_text()
        needle="source.hash(&mut hash);"
        assert original.count(needle)==1
        counted=original.replace(needle,'eprintln!("HASH:{}", source.len());\n            '+needle)
        hook="    // Definitions emit no HTML."
        assert counted.count(hook)==1
        path.write_text(counted.replace(hook, '    if source.contains("FAULT_ERR") { anyhow::bail!("ERR"); }\n'
            '    if source.contains("FAULT_PANIC") { panic!("PANIC"); }\n'+hook))
        cmd("cargo","build","--locked","--release","-p",PKG)
        shutil.copy2(exe,root/(arm+"-count"))
        path.write_text(original)
    compare(root)
    recovery(root)
