#!/usr/bin/env python3
"""Exact build, known environment diagnosis, real worker wire and allocator parity."""
import hashlib
import json
import os
from pathlib import Path
import subprocess as sp
import sys
import tempfile

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-mermaid-render"
DIR = "packages/mermaid-render"
PATCH = HERE/"source.patch"
THEME = {
    "foreground":"#e8e8ed","background":"#11131a","muted":"#8b8d98",
    "border":"#424454","accent":"#8aabff","danger":"#ff7e88",
    "surface":"#242633","surface_alt":"#303344",
    "font_family":"Inter, sans-serif","font_family_mono":"monospace",
}
SOURCE = "flowchart LR\n A[Привет 🦀] --> B[Мир]"


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",",":")).encode()


def frames():
    hello = {"type":"hello","protocol":4,"workspace":"/fixture",
             "features":["surfaces.content.v1","surfaces.preview.v1","widgets.svg.v1"]}
    common = {"context":"test","session_dir":"/fixture","view":"diagram"}
    source_limit = SOURCE + " "*(50_000-len(SOURCE.encode()))
    request_limit = 512*1024
    padded = dict(THEME, fixture_padding="")
    padded["fixture_padding"] = "x"*(request_limit-len(encode({"source":SOURCE,"theme":padded})))
    assert len(encode({"source":SOURCE,"theme":padded})) == request_limit
    endpoints = [
        ("first","content","mermaid",SOURCE,{"theme":THEME},"view"),
        ("repeat","content","mermaid",SOURCE,{"theme":THEME},"view"),
        ("change-theme","content","mermaid",SOURCE,{"theme":dict(THEME,foreground="#112233")},"view"),
        ("preview","preview","text/plain","ignored",{"theme":THEME},"view"),
        ("missing-theme","content","mermaid",SOURCE,{},"content_error"),
        ("null-theme","content","mermaid",SOURCE,{"theme":None},"content_error"),
        ("wrong-language","content","svg",SOURCE,{"theme":THEME},"content_error"),
        ("source-at","content","mermaid",source_limit,{"theme":THEME},"view"),
        ("source-over","content","mermaid",source_limit+"x",{"theme":THEME},"content_error"),
        ("request-at","content","mermaid",SOURCE,{"theme":padded},"view"),
        ("request-over","content","mermaid",SOURCE,{"theme":dict(padded,fixture_padding=padded["fixture_padding"]+"x")},"content_error"),
        ("invalid-diagram","content","mermaid","not-a-diagram Привет",{"theme":THEME},"content_error"),
        ("recover","content","mermaid","sequenceDiagram\n Аня->>Борис: Готово",{"theme":THEME},"view"),
    ]
    messages = [hello]
    for rev, (name,surface,language,source,ctx,kind) in enumerate(endpoints,1):
        messages.append({"type":"render","surface":surface,**common,"content":{
            "language":language,"source":source,"source_revision":rev,"context":ctx}})
        if name=="first":
            messages.append({"type":"render","surface":"content",**common,"view":"second","content":{
                "language":"mermaid","source":"sequenceDiagram\n X->>Y: Hello","source_revision":100,"context":{"theme":THEME}}})
    messages.extend([{"type":"close",**common,"view":"second"}, {"type":"close",**common}])
    expected = {i+1:(row[0],row[-1]) for i,row in enumerate(endpoints)}
    expected[100] = ("second","view")
    return b"".join(encode(m)+b"\n" for m in messages),expected


def worker_wire(binary,cwd,env):
    payload,expected = frames()
    result=sp.run([binary],input=payload,cwd=cwd,env=env,capture_output=True,check=True,timeout=15)
    assert not result.stderr, result.stderr
    replies={}
    for line in result.stdout.splitlines():
        row=json.loads(line)
        rev=row["source_revision"]
        assert rev not in replies and rev in expected, row
        name,kind=expected[rev]
        assert row["type"]==kind, (name,row)
        replies[rev]=row
    assert set(replies)==set(expected)
    assert replies[1]["root"]==replies[2]["root"]==replies[8]["root"]==replies[10]["root"]
    assert replies[3]["root"]!=replies[1]["root"] and "#112233" in replies[3]["root"]["source"]
    assert "Запрос" in replies[4]["root"]["source"] and "ignored" not in replies[4]["root"]["source"]
    assert replies[5]["error"]==replies[6]["error"]
    assert replies[7]["error"]=="unsupported Mermaid language"
    assert replies[9]["error"]=="Mermaid source exceeds 50,000 bytes"
    assert replies[11]["error"]=="Mermaid request is too large"
    assert "Готово" in replies[13]["root"]["source"]
    return result.stdout


def test_package(src,env,profile,arm):
    opts=["--release"] if profile=="release" else []
    cmd=["cargo","test","--locked","-p",PKG,"--no-fail-fast",*opts]
    result=sp.run(cmd,cwd=src,env=env,stdout=sp.PIPE,stderr=sp.STDOUT)
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.buffer.flush()
    if result.returncode==0:
        print("package",arm,profile,"PASS",flush=True)
        return "PASS"
    log=result.stdout.decode(errors="replace")
    # Same unrelated procfs precondition on both arms. Do not cause a broken
    # source/unit test to be reported as an environment failure.
    assert log.count("test result: FAILED.")==1 and "error: 1 target failed:" in log, log
    assert "different_sessions_share_one_worker_and_last_close_and_eof_reap_it" in log
    assert "packages/mermaid-render/tests/wire.rs:155:5" in log
    assert "left: 0" in log and "right: 1" in log
    assert "`-p extension-mermaid-render --test wire`" in log
    print("package",arm,profile,"FAIL (Mermaid /proc child count)",flush=True)
    return "ENV_FAIL"


with tempfile.TemporaryDirectory(prefix="r48-mermaid-borrowed-") as name:
    root = Path(name)
    src = root/"src"
    target = Path(os.environ.get("R48_TARGET", str(root/"target"))).resolve()
    env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_INCREMENTAL="0",TZ="UTC")
    sp.run(["git","clone","--quiet","--shared","--no-checkout",str(Path(sys.argv[1]).resolve()),src],check=True)

    def run(*args):
        sp.run(args,cwd=src,env=env,check=True)

    run("git","checkout","--quiet","--detach",BASE)
    run("git","apply","--index","--check",PATCH)
    wires,requests,status,metrics={},{},{},{}
    for arm in ("stock","candidate"):
        print("ARM",arm,flush=True)
        if arm=="candidate":
            run("git","apply","--whitespace=error",PATCH)
            run("git","apply","--reverse","--check",PATCH)
            run("git","diff","--check")
            run("cargo","fmt","--check","-p",PKG)
        for profile in ("debug","release"):
            status[arm,profile]=test_package(src,env,profile,arm)
        run("node","--test",f"{DIR}/tests/worker.test.mjs")
        exe=target/"release/mermaid-render"
        wires[arm]=worker_wire(exe,src/DIR,env)
        main=src/DIR/"src/main.rs"
        original=main.read_text()
        assert original.count("fn main() {")==1
        method=("render_request(content.source.as_str(), content.context.get(\"theme\")).unwrap()"
                if arm=="candidate" else "render_request(&content).to_string()")
        main.write_text(original.replace("fn main() {","#[allow(dead_code)]\nfn process_main() {")
            +"\n"+(HERE/"probe.rs").read_text().replace("__BUILD__",method))
        run("cargo","build","--locked","--release","-p",PKG)
        requests[arm]=sp.check_output([exe,"wire"],env=env)
        metrics[arm]=sp.check_output([exe,"measure"],env=env)
        assert all(sp.check_output([exe,"measure"],env=env)==metrics[arm] for _ in range(4))
        main.write_text(original)
    assert all(status["stock",profile]==status["candidate",profile] for profile in ("debug","release"))
    for label, outputs in (("wire",wires),("request",requests)):
        assert outputs["stock"]==outputs["candidate"]
        print(label,"identical",len(outputs["stock"]),"bytes",hashlib.sha256(outputs["stock"]).hexdigest(),flush=True)
    print("arm case source_B request_B alloc_calls requested_B")
    for arm,lines in metrics.items():
        for line in lines.decode().splitlines():
            print(arm,line)
    for l,r in zip(metrics["stock"].splitlines(),metrics["candidate"].splitlines(),strict=True):
        fields_l=l.split(); fields_r=r.split()
        assert fields_l[:3]==fields_r[:3] and int(fields_r[4])<int(fields_l[4]), (l,r)
