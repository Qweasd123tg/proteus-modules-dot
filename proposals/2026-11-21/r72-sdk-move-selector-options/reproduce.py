#!/usr/bin/env python3
"""Pinned-selector parity with per-arm fresh Cargo artifacts and measured scopes."""
import argparse
import fcntl
from hashlib import sha256
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess as sp
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit

import fixtures

HERE = Path(__file__).resolve().parent
PIN = "892f627570369ed60d7205eb0d351c753ec4305f"
M150 = "60c98d197045c6d41d5f568cf44a106c0ec89d9aed13028ea6dd463568a24ac8"
OVERLAYS = [
    "3d85e07b31b7d7e14ccaa299e9fdafe5a2bb27aa95e858e97f3ebd9dacf981b9",
    "5a22007dbd5cc4a806aa40e2faccf0fa06ee2ea4bd45e38ba59634d9152c713a",
]
SDK = "sdk/Cargo.toml"
USAGE = "packages/usage/Cargo.toml"
MODEL = "packages/model/Cargo.toml"
PROBE = "r72_option_probe"
FLAGS = ["--release","--locked","--offline","-j1"]
SCOPE = ["-p","proteus-extension","-p","extension-model","-p","extension-usage"]
TEST_COUNTS = rb"^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;"


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def source_tree(path, omit_git=False):
    rows = []
    for entry in sorted(path.rglob("*")):
        rel = entry.relative_to(path)
        if omit_git and ".git" in rel.parts:
            continue
        if entry.is_symlink():
            rows.append([str(rel),"link",str(entry.readlink())])
        elif entry.is_file():
            rows.append([str(rel),"x" if entry.stat().st_mode & 0o111 else "-",hash_file(entry)])
    return sha256(json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def usage_model_wire(usage, model, env, src):
    r = {}
    reads = []

    class Server(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            q = parse_qs(url.query,keep_blank_values=True)
            assert q == {"session_dir":[fixtures.SESSION]} and self.headers["Authorization"] == "Bearer fixture"
            table = {"/sessions":fixtures.session_summaries,"/usage":fixtures.usage_snapshot}
            payload = json.dumps(table[url.path](),ensure_ascii=False).encode()
            reads.append((url.path,q["session_dir"][0]))
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with http.server.ThreadingHTTPServer(("127.0.0.1",0),Server) as server:
        worker = threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.05},daemon=True)
        worker.start()
        try:
            for exe,name,trace,check in [
                (usage,"usage",fixtures.trace_usage,lambda frames:fixtures.assert_usage(frames,reads)),
                (model,"model",fixtures.trace_model,fixtures.assert_model),
            ]:
                folder = src / "packages" / name
                features = json.loads((folder/"extension.json").read_text())["required_features"]
                origin = f"http://127.0.0.1:{server.server_port}" if name=="usage" else ""
                p = sp.run([exe],cwd=folder,env=env,timeout=15,check=True,capture_output=True,
                           input=fixtures.input_bytes(trace(),features,origin))
                assert not p.stderr,p.stderr
                frames = [json.loads(line) for line in p.stdout.splitlines()]
                check(frames)
                assert not any(f["type"]=="set_session" for f in frames), frames
                r[name] = p.stdout
        finally:
            server.shutdown()
            worker.join()
    return r,reads


def control_sizes(a,b):
    for left,right in zip(a.decode().splitlines(),b.decode().splitlines(),strict=True):
        k,name,n,calls,bytes_,capacity = left.split()
        k1,name1,n1,calls1,bytes1,capacity1 = right.split()
        assert (k,name,n)==(k1,name1,n1) and capacity==capacity1,(left,right)
        if name in {"empty","unchanged-control"}:
            assert left==right,(left,right)
        else:
            assert int(calls1)<int(calls) and int(bytes1)<int(bytes_),(left,right)
            if name in {"ordinary-large","large"}:
                assert int(bytes_)-int(bytes1)>=36*int(n),(left,right)


def run(target, env, cwd, *cmd):
    with tempfile.TemporaryFile(dir=HERE) as stdout, tempfile.TemporaryFile(dir=HERE) as stderr:
        with sp.Popen(cmd,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True) as child:
            try:
                while True:
                    try:
                        status = child.wait(timeout=2)
                        break
                    except sp.TimeoutExpired:
                        if min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)<256*2**20:
                            raise RuntimeError("disk stop floor")
            except BaseException:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except sp.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL)
                        child.wait()
                raise
        stdout.seek(0)
        stderr.seek(0)
        actual,error=stdout.read(),stderr.read()
    if status!=0:
        raise RuntimeError((cmd,status,actual.decode(errors="replace"),error.decode(errors="replace")))
    return actual


def cargo_events(raw):
    rows = [json.loads(line) for line in raw.splitlines() if line.lstrip().startswith(b"{")]
    assert [r.get("success") for r in rows if r.get("reason")=="build-finished"]==[True]
    return [r for r in rows if r.get("reason")=="compiler-artifact"]


def select_artifact(events, src, manifest, source_path, name, kind, test, executable=True):
    target_file=src/source_path
    entries=[
        entry for entry in events if Path(entry["manifest_path"]).resolve()==src/manifest
        and entry["target"]["name"]==name and entry["target"]["kind"]==[kind]
        and Path(entry["target"]["src_path"]).resolve()==target_file
        and entry["profile"]["test"] is test
        and bool(entry["executable"])==executable
    ]
    assert len(entries)==1,(manifest,source_path,name,kind,test,len(entries))
    return entries[0]


def artifact_receipt(event, target, phase, manifest, input_hash, compiler):
    if event["executable"]:
        files = [event["executable"]]
    else:
        files = [name for name in event["filenames"] if name.endswith((".rlib",".rmeta"))]
        assert files and any(name.endswith(".rlib") for name in files),files
    fingerprints = {}
    for real in files:
        physical=Path(real).resolve(strict=True)
        assert physical.is_relative_to(target) and physical.is_file(),physical
        if event["executable"]:
            assert physical.stat().st_mode & 0o111,physical
        fingerprints[physical.relative_to(target).as_posix()]={"sha256":hash_file(physical),
                                                              "bytes":physical.stat().st_size}
    receipt={
        "phase":phase,"manifest":manifest,"name":event["target"]["name"],"kind":event["target"]["kind"],
        "test":event["profile"]["test"],"fresh":event["fresh"],"source_sha256":input_hash,
        "toolchain_sha256":compiler,"files":fingerprints,
    }
    print("artifact",json.dumps(receipt,sort_keys=True),flush=True)
    return fingerprints


def check_files(target, records):
    for path,signature in records.items():
        item=(target/path).resolve(strict=True)
        assert item.is_relative_to(target) and item.is_file()
        assert item.stat().st_size==signature["bytes"] and hash_file(item)==signature["sha256"],path


def assert_suite(raw,count):
    assert [tuple(map(int,row)) for row in re.findall(TEST_COUNTS,raw,re.M)]==[(count,0,0,0,0)],raw[-2000:]


def arm(root, tier, variant, args, target, env, toolchain):
    src=root/(tier+"-"+variant)
    patch=HERE/"source.patch"
    overlays=[]
    if tier=="base":
        sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",args.stock_git,src],check=True)
        run(target,env,src,"git","checkout","-q","--detach",PIN)
        assert run(target,env,src,"git","rev-parse","HEAD").decode().strip()==PIN
    else:
        shutil.copytree(args.m150_source,src,symlinks=True,copy_function=shutil.copy)
        assert source_tree(src)==M150
        for prior in args.prior:
            run(target,env,src,"git","apply","--check","--whitespace=error",prior)
            run(target,env,src,"git","apply","--whitespace=error",prior)
            overlays.append(hash_file(prior))
    run(target,env,src,"git","apply","--check","--whitespace=error",patch)
    if variant=="candidate":
        run(target,env,src,"git","apply","--whitespace=error",patch)
        run(target,env,src,"git","apply","--reverse","--check",patch)
        overlays.append(hash_file(patch))
    run(target,env,src,"cargo","fmt","-p","proteus-extension","--","--check")
    before = source_tree(src,omit_git=True)
    compiler = sha256(json.dumps(toolchain,sort_keys=True).encode()).hexdigest()
    print("arm",json.dumps({"tier":tier,"variant":variant,"source_sha256":before,"pin":PIN,
          "overlays":overlays,"lock_sha256":hash_file(src/"Cargo.lock"),"toolchain_sha256":compiler,
          "sdk_ui_sha256":hash_file(src/"sdk/src/ui.rs")},sort_keys=True),flush=True)
    counts=(60,10,12) if tier=="base" else (65,11,15)
    counts=(counts[0]+(variant=="candidate"),counts[1],counts[2])

    events=cargo_events(run(target,env,src,"cargo","test","--no-run",*FLAGS,*SCOPE,"--message-format=json"))
    production = select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
    assert production["fresh"] is False,"SDK was not built freshly in this arm"
    sdk_files=artifact_receipt(production,target,tier+"/"+variant+"/unit-dependency",SDK,before,compiler)

    for (manifest,file,name,kind),size in zip([
        (SDK,"sdk/src/lib.rs","proteus_extension","lib"),
        (MODEL,"packages/model/src/main.rs","model","bin"),
        (USAGE,"packages/usage/src/main.rs","usage","bin"),
    ],counts,strict=True):
        event=select_artifact(events,src,manifest,file,name,kind,True)
        assert event["fresh"] is False,(manifest,"compiled test was cached")
        exe=artifact_receipt(event,target,tier+"/"+variant+"/unit-exe",manifest,before,compiler)
        check_files(target,exe)
        raw=run(target,env,(src/manifest).parent,target/next(iter(exe)))
        check_files(target,exe)
        assert_suite(raw,size)
        print("unit-pass",tier,variant,name,size,flush=True)
    assert_suite(run(target,env,src,"cargo","test","--doc",*FLAGS,"-p","proteus-extension"),1)
    print("doc-pass",tier,variant,"proteus_extension",1,flush=True)

    def linked_sdk(events, phase, source_hash):
        nonlocal sdk_files
        packaged=select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
        seen=artifact_receipt(packaged,target,tier+"/"+variant+"/"+phase,SDK,source_hash,compiler)
        if packaged["fresh"]:
            assert seen==sdk_files,"cached SDK does not match this arm's verified library"
        else:
            sdk_files=seen
        check_files(target,sdk_files)

    events=cargo_events(run(target,env,src,"cargo","build",*FLAGS,"-p","extension-model","-p","extension-usage",
                            "--bins","--message-format=json"))
    linked_sdk(events,"wire-dependency",before)
    built={}
    for file,name in [(MODEL,"model"),(USAGE,"usage")]:
        event=select_artifact(events,src,file,f"packages/{name}/src/main.rs",name,"bin",False)
        assert event["fresh"] is False,(file,"wire binary was cached")
        built[name]=artifact_receipt(event,target,tier+"/"+variant+"/wire-exe",file,before,compiler)
        check_files(target,built[name])
    wire = usage_model_wire(target/next(iter(built["usage"])),target/next(iter(built["model"])),env,src)
    for r in built.values():
        check_files(target,r)

    assert source_tree(src,omit_git=True)==before
    example_rel = f"sdk/examples/{PROBE}.rs"
    example = src/example_rel
    assert not example.exists()
    example.parent.mkdir(exist_ok=True)
    shutil.copyfile(HERE/"probe.rs",example)
    probe_source = source_tree(src,omit_git=True)
    print("probe-source",json.dumps({"tier":tier,"variant":variant,"source_sha256":probe_source,
          "arm_source_sha256":before,"probe_sha256":hash_file(example),"toolchain_sha256":compiler},sort_keys=True),flush=True)
    events=cargo_events(run(target,env,src,"cargo","build",*FLAGS,"-p","proteus-extension","--example",
                            PROBE,"--message-format=json"))
    linked_sdk(events,"probe-dependency",probe_source)
    probe_event=select_artifact(events,src,SDK,example_rel,PROBE,"example",False)
    assert probe_event["fresh"] is False,"probe executable was cached in this arm"
    proof=artifact_receipt(probe_event,target,tier+"/"+variant+"/probe-exe",SDK,probe_source,compiler)
    check_files(target,proof)
    exe=target/next(iter(proof))
    results=run(target,env,src,exe,"wire")
    meters=run(target,env,src,exe,"counts")
    assert all(run(target,env,src,exe,"counts")==meters for _ in range(4))
    check_files(target,proof)
    check_files(target,sdk_files)
    assert source_tree(src,omit_git=True)==probe_source
    return wire,results,meters


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_git",type=Path)
    p.add_argument("m150_source",type=Path)
    p.add_argument("prior",type=Path,nargs=2)
    p.add_argument("--target",required=True,type=Path)
    p.add_argument("--lock",required=True,type=Path)
    p.add_argument("--admit-exclusive",action="store_true")
    a=p.parse_args()
    a.stock_git=a.stock_git.resolve(strict=True)
    a.m150_source=a.m150_source.resolve(strict=True)
    a.prior=[item.resolve(strict=True) for item in a.prior]
    target=a.target.resolve(strict=True)
    assert target.is_dir() and Path(os.environ["CARGO_HOME"]).is_dir()
    assert source_tree(a.m150_source)==M150 and [hash_file(item) for item in a.prior]==OVERLAYS
    print("preflight free source, target bytes",shutil.disk_usage(HERE).free,shutil.disk_usage(target).free,flush=True)
    if not a.admit_exclusive:
        print("Read-only preflight: compiler not started")
        return
    with a.lock.resolve(strict=True).open("rb") as gate:
        fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)>=512*2**20
        env = dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_NET_OFFLINE="true",
                   CARGO_INCREMENTAL="0",CARGO_BUILD_JOBS="1",TZ="UTC",LC_ALL="C")
        chain={}
        for tool, args in [("rustc",["-Vv"]),("rustdoc",["--version"]),("cargo",["--version"]),("rustfmt",["--version"])]:
            binary=Path(shutil.which(tool,path=env["PATH"])).resolve(strict=True)
            chain[tool]={"sha256":hash_file(binary),"version":run(target,env,HERE,binary,*args).decode().strip()}
        assert "release: 1.95.0" in chain["rustc"]["version"]
        print("toolchain",json.dumps(chain,sort_keys=True),flush=True)
        with tempfile.TemporaryDirectory(prefix="selector-r72-",dir=HERE) as spool:
            for tier in ("base","M150+394+395"):
                arms=[arm(Path(spool),tier,variant,a,target,env,chain) for variant in ("stock","candidate")]
                stock,candidate=arms
                assert stock[:2]==candidate[:2],tier
                control_sizes(stock[2],candidate[2])
                print(tier,"synthetic ordered GET",stock[0][1])
                for name,value in stock[0][0].items():
                    print(tier,"ordinary",name,len(value.splitlines()),len(value),sha256(value).hexdigest())
                print(tier,"probe outputs",len(stock[1].splitlines()),len(stock[1]),sha256(stock[1]).hexdigest())
                for name,(_,_,meters) in zip(("stock","candidate"),arms,strict=True):
                    for line in meters.decode().splitlines():
                        print(tier,"meter",name,line)
        assert source_tree(a.m150_source)==M150 and [hash_file(p) for p in a.prior]==OVERLAYS


if __name__=="__main__":
    main()
