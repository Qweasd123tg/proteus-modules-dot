#!/usr/bin/env python3
"""Exact scoped Rust gates, clean process wire, and separate selector counters."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess as sp
import sys
import tempfile

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
M150 = "60c98d197045c6d41d5f568cf44a106c0ec89d9aed13028ea6dd463568a24ac8"
HERE = Path(__file__).resolve().parent
SCOPE = ["-p","proteus-extension","-p","extension-mode","-p","extension-model"]
SESSION = "/setting-fixture"
SESSION_B = "/setting-other"
NO_SECRET = "fixture denied"

DATA = {
    "mode": ("normal", [("normal","Normal"),("plan","Read fixture")]),
    "behavior_mode": ("_default", [("_default","Profile"),("review","Review")]),
    "model": ("model-a", [("model-a","Fixture A"),("model-b","Fixture B")]),
    "reasoning_effort": ("effort:high", [("_default","Default"),("effort:low","Low"),("effort:high","High")]),
    "style": ("short", [("short","Short"),("long","Long")]),
    "tone": ("plain", [("plain","Plain"),("dry","Dry")]),
}


def setting(id, kind="select"):
    current, choices = DATA[id]
    return {"id":id,"name":id,"control":{"type":kind,"value":current,
             "options":[{"value":value,"name":label} for value,label in choices]}}


def config(package, n, fault=False, other=False):
    if package == "mode":
        rows = [setting("mode"),setting("behavior_mode","slider"),setting("behavior_mode")]
        if other:
            rows[0]["control"]["value"] = "plan"
    else:
        rows = [setting("mode"),setting("model"),setting("reasoning_effort","slider"),
                setting("reasoning_effort"),setting("style"),setting("tone")]
        if other:
            rows[1]["control"]["value"] = "model-b"
    # Malformed rows interleaved with non-select controls do not add Model extras.
    rows += [{"id":f"hidden-{i}","control":{"type":"slider","value":i}} if i % 2 else None
             for i in range(n - len(rows))]
    result = {"profile":"Fixture","model":{"provider":"fixture","name":"model-a"},
              "model_options":[{"provider":"fixture","name":"model-a"},{"provider":"other","name":"model-b"}],
              "session_settings":rows}
    if fault:
        result["model_catalog_error"] = "fixture catalogue missing"
    return result


def initial(package, needed):
    return [{"type":"hello","protocol":4,"features":needed,"workspace":"/project-fixture"}]


def snapshot(package, n, *, context="one", session=SESSION, **kwargs):
    return {"type":"session_snapshot","context":context,"session_dir":session,
            "state":{"config":config(package,n,**kwargs)}}


def render(surface, *, context="one", session=SESSION, view=None):
    return {"type":"render","context":context,"session_dir":session,"view":view or surface,"surface":surface}


def close(view):
    return {"type":"close","view":view}


def action(view, name, value, sequence):
    return {"type":"action","view":view,"action":name,"value":value,"sequence":sequence}


def process(exe, messages, *, env, counts=False):
    result = sp.run([exe],input=b"".join(json.dumps(msg).encode() + b"\n" for msg in messages),
                    capture_output=True,check=True,timeout=15,env=env)
    if not counts:
        assert not result.stderr,result.stderr
    return result.stdout,result.stderr


def ordinary(exe, package, needed, env):
    messages = initial(package,needed) + [
        snapshot(package,8),render("badge"),render("popup"),close("badge"),
        action("popup","mode" if package == "mode" else "effort","unknown",1),
        action("popup","mode" if package == "mode" else "effort","plan" if package == "mode" else 0,2),
        snapshot(package,8,context="two",session=SESSION_B,other=True),
        render("badge",context="two",session=SESSION_B,view="badge-other"),
        close("badge-other"),
        {"type":"context","context":"destination","workspace":"/project-fixture","session_dir":SESSION},
        {"type":"rehost","view":"popup","context":"destination"},
        {"type":"close_context","context":"one"},
        {"type":"command_result","context":"one","id":"setting-1","session_dir":SESSION,
         "config":None,"error":NO_SECRET},
        render("badge",context="destination",session=SESSION,view="badge-denied"),
        close("badge-denied"),close("popup"),
        snapshot(package,8,context="destination",fault=True),
        render("popup",context="destination"),close("popup"),
        render("preview",context="preview",session=None),close("preview"),
    ]
    body,_ = process(exe,messages,env=env)
    frames = [json.loads(line) for line in body.splitlines()]
    receipts = [r for r in frames if r["type"] == "set_session"]
    assert len(receipts) == 1 and receipts[0]["view"] == "popup"
    assert receipts[0]["setting"] == ({"id":"mode","value":"plan"} if package == "mode"
                                     else {"id":"reasoning_effort","value":"effort:low"})
    assert receipts[0]["context"] == "one" and receipts[0]["session_dir"] == SESSION
    assert any(r.get("view") == "preview" and r["type"] == "view" for r in frames)
    assert not any(NO_SECRET in json.dumps(r,ensure_ascii=False) for r in frames if r.get("session_dir") == SESSION_B)
    assert any(r.get("view") == "badge-other" and r.get("session_dir") == SESSION_B for r in frames)
    assert any(r.get("view") == "badge-denied" and NO_SECRET in r.get("lines",[]) for r in frames)
    if package == "model":
        assert b"catalog-error" in body
    return body


def instrument(src, arm):
    host = src / "sdk/src/host.rs"
    rust = host.read_text()
    bulk = "pub fn session_settings(&self) -> Vec<&Value> {"
    assert rust.count(bulk) == 1
    rust = rust.replace(bulk,bulk + "\n        BULK_VECTORS.fetch_add(1, Relaxed);")
    marker = ('|setting| setting.at("control").str("type") == "select"' if arm == "stock"
              else '|setting| {\n                let control = setting.at("control");')
    insertion = ('|setting| {ROW_CHECKS.fetch_add(1,Relaxed); setting.at("control").str("type") == "select"}'
                 if arm == "stock" else marker + "\n                ROW_CHECKS.fetch_add(1, Relaxed);")
    assert rust.count(marker) == 1
    host.write_text(rust.replace(marker,insertion) + "\n" + (HERE / "probe.rs").read_text())
    exports = src / "sdk/src/lib.rs"
    exports.write_text(exports.read_text() + "\npub use host::{selector_probe_snapshot, selector_probe_controls};\n")
    for package in ("mode","model"):
        main = src / f"packages/{package}/src/main.rs"
        source = main.read_text()
        marker = f"fn main() {{\n    run({package.title()}::default());\n}}"
        assert source.count(marker) == 1
        main.write_text(source.replace(marker, marker[:-1] + """    let (checks, bulk) = proteus_extension::selector_probe_snapshot();
    eprintln!("{checks} {bulk}");
}""").replace("fn main() {","""fn main() {
    if std::env::args().nth(1).as_deref() == Some("direct") {
        println!("{}", proteus_extension::selector_probe_controls());
        return;
    }""",1))


def sample(exe, package, needed, env):
    rows = []
    wire = []
    for n in (8,64):
        for surface in ("badge","popup"):
            m = initial(package,needed) + [snapshot(package,n),render(surface),close(surface)]
            out,stats = process(exe,m,env=env,counts=True)
            frames = [json.loads(line) for line in out.splitlines()]
            assert len(frames) == 1 and frames[0]["view"] == surface,frames
            rows.append((package,n,surface,*map(int,stats.decode().split())))
            wire.append(out)
    return rows,wire


def command_runner(src, env):
    def go(*cmd):
        with tempfile.TemporaryFile() as out:
            with sp.Popen(cmd,cwd=src,env=env,stdout=out,stderr=sp.STDOUT,start_new_session=True) as child:
                try:
                    while True:
                        try:
                            code = child.wait(timeout=2)
                            break
                        except sp.TimeoutExpired:
                            assert min(shutil.disk_usage(src).free,shutil.disk_usage(env["CARGO_TARGET_DIR"]).free) >= 256*2**20, "disk stop floor"
                except BaseException:
                    if child.poll() is None:
                        os.killpg(child.pid,signal.SIGTERM)
                        try:
                            child.wait(timeout=10)
                        except sp.TimeoutExpired:
                            os.killpg(child.pid,signal.SIGKILL)
                            child.wait()
                    raise
            out.seek(0)
            data = out.read()
        if code:
            raise RuntimeError((cmd,code,data.decode()))
        return data.decode()
    return go


def verify_tests(go, profile, expected, arm, tier):
    flags = ["--release"] if profile == "release" else []
    output = go("cargo","test","--locked","--offline","--no-fail-fast","-j1",*SCOPE,*flags)
    summaries = re.findall(r"^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;",output,re.M)
    assert [tuple(map(int,row)) for row in summaries] == [(n,0,0,0,0) for n in expected],summaries
    print(tier,arm,profile,"Mode, Model, SDK/lib, SDK/doc passes:",*expected,flush=True)


def base_replay(root, checkout, target, env):
    src = root / "source"
    sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",checkout,src],check=True)
    go = command_runner(src,env)
    saved = {}
    go("git","checkout","-q","--detach",BASE)
    assert go("git","rev-parse","HEAD").strip() == BASE
    patch = HERE / "source.patch"
    inputs = ["sdk/src/host.rs","sdk/src/lib.rs","packages/mode/src/main.rs","packages/model/src/main.rs"]
    for arm, expected in [("stock",(4,10,60,1)),("candidate",(4,10,62,1))]:
        go("git","apply","--check","--index",patch)
        if arm == "candidate":
            go("git","apply","--whitespace=error",patch)
            go("git","apply","--reverse","--check",patch)
            go("git","diff","--check")
        go("cargo","fmt","--all","--","--check")
        for profile in ("debug","release"):
            verify_tests(go,profile,expected,arm,"base")
        go("cargo","build","--release","--locked","--offline","-j1",*SCOPE)
        features = {p:json.loads((src / f"packages/{p}/extension.json").read_text())["required_features"] for p in ("mode","model")}
        normal = {p:ordinary(target / "release" / p,p,features[p],env) for p in features}
        originals = {name:(src / name).read_bytes() for name in inputs}
        instrument(src,arm)
        go("cargo","build","--release","--locked","--offline","-j1",*SCOPE)
        counts,mini = [],[]
        for package in features:
            exe = target / "release" / package
            rows, wire = sample(exe,package,features[package],env)
            assert all(sample(exe,package,features[package],env)==(rows,wire) for _ in range(4))
            counts.extend(rows)
            mini.extend(wire)
        raw = go(target / "release" / "mode","direct")
        assert all(go(target / "release" / "mode","direct")==raw for _ in range(4))
        saved[arm] = normal,mini,counts,json.loads(raw)
        for name,data in originals.items():
            (src / name).write_bytes(data)
        if arm == "stock":
            go("git","update-index","-q","--refresh")
            go("git","diff","--exit-code")
    a,b = saved.values()
    assert a[:2] == b[:2]
    for p,out in a[0].items():
        print("ordinary",p,len(out.splitlines()),len(out),sha256(out).hexdigest())
    joined = b"".join(a[1])
    print("instrumented one-render frames",len(joined.splitlines()),len(joined),sha256(joined).hexdigest())
    check = {"stock":{("mode",8,"badge"):(40,5),("mode",8,"popup"):(32,4),
                     ("mode",64,"badge"):(320,5),("mode",64,"popup"):(256,4),
                     ("model",8,"badge"):(40,5),("model",8,"popup"):(64,8),
                     ("model",64,"badge"):(320,5),("model",64,"popup"):(512,8)},
             "candidate":{("mode",8,"badge"):(9,0),("mode",8,"popup"):(8,0),
                          ("mode",64,"badge"):(9,0),("mode",64,"popup"):(8,0),
                          ("model",8,"badge"):(16,0),("model",8,"popup"):(35,1),
                          ("model",64,"badge"):(16,0),("model",64,"popup"):(91,1)}}
    print("case, rows, surface, select predicates, list vectors: five exact repeats per arm")
    for arm,(_,_,rows,control) in saved.items():
        assert {(p,n,s):(x,v) for p,n,s,x,v in rows} == check[arm],rows
        assert [r[:3] for r in control] == [["empty",False,None],["missing-64",False,None],
                                          ["last-64",True,"last"],["pending-null",True,None]]
        assert [r[3:] for r in control] == ([[0,1],[64,1],[64,1],[0,0]] if arm == "stock"
                                            else [[0,0],[64,0],[64,0],[0,0]])
        for row in rows:
            print(arm,*row)
        print(arm,"controls",json.dumps(control))


def tree(path):
    rows = []
    for p in sorted(path.rglob("*")):
        if p.is_symlink():
            rows.append([str(p.relative_to(path)),"link",str(p.readlink())])
        elif p.is_file():
            rows.append([str(p.relative_to(path)),"x" if p.stat().st_mode & 0o111 else "-",sha256(p.read_bytes()).hexdigest()])
    return sha256(json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def cumulative(root, source, target, env):
    assert tree(source) == M150
    src = root / "cumulative"
    # A reused target may hold a diagnostic binary from the previous arm.
    # Retain file bytes/modes/links but deliberately use fresh source mtimes.
    shutil.copytree(source,src,symlinks=True,copy_function=shutil.copy)
    assert tree(src) == M150
    go = command_runner(src,env)
    patch = HERE / "source.patch"
    go("git","apply","--check","--whitespace=error",patch)
    arms = []
    for arm, expected in [("stock",(4,11,62,1)),("candidate",(4,11,64,1))]:
        if arm == "candidate":
            go("git","apply","--whitespace=error",patch)
            go("git","apply","--reverse","--check",patch)
        verify_tests(go,"release",expected,arm,"M150")
        go("cargo","build","--release","--locked","--offline","-j1",*SCOPE)
        features = {p:json.loads((src / f"packages/{p}/extension.json").read_text())["required_features"] for p in ("mode","model")}
        arms.append({p:ordinary(target / "release" / p,p,features[p],env) for p in features})
    assert arms[0] == arms[1]
    for p,out in arms[0].items():
        print("M150 ordinary",p,len(out.splitlines()),len(out),sha256(out).hexdigest())
    go("git","apply","--reverse","--whitespace=error",patch)
    assert tree(src) == tree(source) == M150


def main():
    checkout = Path(sys.argv[1]).resolve(strict=True)
    m150 = Path(sys.argv[2]).resolve(strict=True) if len(sys.argv) > 2 else None
    with tempfile.TemporaryDirectory(prefix="sdk-lazy-select-") as directory:
        root = Path(directory)
        target = Path(os.environ.get("R69_EXT_TARGET",root / "target")).resolve()
        target.mkdir(parents=True,exist_ok=True)
        assert min(shutil.disk_usage(root).free,shutil.disk_usage(target).free) >= 512*2**20
        env = dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_INCREMENTAL="0",TZ="UTC")
        base_replay(root,checkout,target,env)
        if m150 is not None:
            cumulative(root,m150,target,env)


if __name__ == "__main__":
    main()
