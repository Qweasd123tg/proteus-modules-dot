#!/usr/bin/env python3
"""Exact release-only comparison for the layout child ownership patch."""
import argparse
from hashlib import sha256
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

HERE = Path(__file__).resolve().parent
PIN = "892f627570369ed60d7205eb0d351c753ec4305f"
M150 = "60c98d197045c6d41d5f568cf44a106c0ec89d9aed13028ea6dd463568a24ac8"
PREVIOUS = "3d85e07b31b7d7e14ccaa299e9fdafe5a2bb27aa95e858e97f3ebd9dacf981b9"
PACKAGES = ("context","mode","model")
SCOPE = sum((["-p","extension-" + s] for s in PACKAGES),[])
SESSION = "/layout-fixture"

def tree(folder):
    rows = []
    for p in sorted(folder.rglob("*")):
        if p.is_symlink():
            rows.append([str(p.relative_to(folder)),"link",str(p.readlink())])
        elif p.is_file():
            rows.append([str(p.relative_to(folder)),"x" if p.stat().st_mode & 0o111 else "-",
                         sha256(p.read_bytes()).hexdigest()])
    return sha256(json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def make_commands(src,env):
    def go(*args):
        with tempfile.TemporaryFile(dir=HERE) as f:
            with sp.Popen(args,cwd=src,env=env,stdout=f,stderr=sp.STDOUT,start_new_session=True) as child:
                try:
                    while True:
                        try:
                            code = child.wait(timeout=2)
                            break
                        except sp.TimeoutExpired:
                            if min(shutil.disk_usage(src).free,shutil.disk_usage(env["CARGO_TARGET_DIR"]).free) < 256*2**20:
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
            f.seek(0)
            raw = f.read()
        if code:
            raise RuntimeError((args,code,raw.decode()))
        return raw
    return go

def choices(id, value, options):
    return {"id":id,"name":id,"control":{"type":"select","value":value,
        "options":[{"name":label,"value":val} for val,label in options]}}

def ordinary(target,src,env):
    result = {}
    queried = []

    class API(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query,keep_blank_values=True)
            assert url.path == "/context" and query == {"session_dir":[SESSION]}
            assert self.headers["Authorization"] == "Bearer fixture"
            queried.append((url.path,query["session_dir"][0]))
            data = {"history":{"messages":20,"user_messages":3,"assistant_messages":5,
                                "tool_results":12,"estimated_tokens":12000},
                    "tools":{"requested":12,"finished":12,"failed":1,"names":["fixture-view"]},
                    "diagnostics":["synthetic context detail"],
                    "latest_context":{"chunks":4,"token_estimate":12000},
                    "latest_usage":{"source":"provider","phase":"request","model_provider":"fixture",
                                    "model_name":"a","max_input_tokens":64000,"compaction_trigger_tokens":54000,
                                    "actual":{"input_tokens":12000,"cached_input_tokens":7000,
                                              "cache_creation_input_tokens":0},
                                    "categories":[{"name":"instructions","tokens":800},
                                                  {"name":"messages","tokens":7400},
                                                  {"name":"tool_results","tokens":3800}]}}
            payload = json.dumps(data,ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with ThreadingHTTPServer(("127.0.0.1",0),API) as server:
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.05},daemon=True)
        thread.start()
        try:
            for name in PACKAGES:
                context={"used":12000,"max":64000,"trigger":54000}
                config={"profile":"Fixture","model":{"provider":"fixture","name":"a"},
                  "session_settings":[
                    choices("mode","normal",[("normal","Normal"),("plan","Read fixture")]),
                    choices("behavior_mode","_default",[("_default","Profile"),("review","Review")]),
                    choices("model","a",[("a","Model A"),("b","Model B")]),
                    choices("reasoning_effort","effort:high",[("_default","Default"),("effort:low","Low"),
                                                              ("effort:high","High")]),
                    choices("style","short",[("short","Brief"),("long","Detailed")])
                ]}
                features=json.loads((src/"packages"/name/"extension.json").read_text())["required_features"]
                hello={"type":"hello","protocol":4,"features":features,
                    "workspace":"/layout-workspace","server":{"origin":f"http://127.0.0.1:{server.server_port}",
                                                               "token":"fixture"}}
                message=[hello,
                    {"type":"render","context":"preview","session_dir":None,"surface":"preview","view":"preview"},
                    {"type":"close","view":"preview"},
                    {"type":"session_snapshot","context":"live","session_dir":SESSION,
                     "state":{"context":context,"config":config}},
                    {"type":"render","context":"live","session_dir":SESSION,"surface":"badge","view":"badge"},
                    {"type":"close","view":"badge"},
                    {"type":"render","context":"live","session_dir":SESSION,"surface":"popup","view":"popup"},
                    {"type":"close","view":"popup"}]
                wire=sp.run([target/"release"/name],input=b"".join(json.dumps(msg).encode()+b"\n" for msg in message),
                            cwd=src/"packages"/name,env=env,capture_output=True,check=True,timeout=15)
                assert not wire.stderr,wire.stderr
                frames=[json.loads(line) for line in wire.stdout.splitlines()]
                assert [(f["type"],f["view"]) for f in frames]==[("view","preview"),("badge","badge"),("view","popup")],frames
                assert frames[-1]["root"]["type"]=="stack" and frames[-1]["root"]["children"],frames[-1]
                result[name]=wire.stdout
        finally:
            server.shutdown()
            thread.join()
    assert queried==[("/context",SESSION)],queried
    return result,queried

def check_counts(baseline,final):
    for a,b in zip(baseline.decode().splitlines(),final.decode().splitlines(),strict=True):
        case,n,calls,requests,capacity=a.split()
        case1,n1,calls1,requests1,capacity1=b.split()
        assert (case,n)==(case1,n1)
        if case in ("fill-control","empty-control"):
            assert a==b,(a,b)
        else:
            assert int(calls1)<int(calls) and int(requests)-int(requests1)>=int(n),(a,b)
            if case=="nested-large":
                assert int(requests)-int(requests1)>=4*int(n),(a,b)
        if case=="row-spare-capacity":
            assert int(capacity1)==64 and int(capacity)<64,(a,b)

def compare(tier,folder,target,stock,m150,previous):
    captured={}
    cumulative=tier=="m150+394"
    for arm in ("stock","candidate"):
        src=folder/(tier+"-"+arm)
        env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_NET_OFFLINE="true",
                 CARGO_INCREMENTAL="0",CARGO_BUILD_JOBS="1",TZ="UTC")
        go=make_commands(src,env)
        if cumulative:
            shutil.copytree(m150,src,symlinks=True,copy_function=shutil.copy)
            assert tree(src)==M150
            go("git","apply","--check","--whitespace=error",previous)
            go("git","apply","--whitespace=error",previous)
        else:
            sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",stock,src],check=True)
            go("git","checkout","-q","--detach",PIN)
            assert go("git","rev-parse","HEAD").decode().strip()==PIN
        patch=HERE/"source.patch"
        go("git","apply","--check","--whitespace=error",patch)
        if arm=="candidate":
            go("git","apply","--whitespace=error",patch)
            go("git","apply","--reverse","--check",patch)
        go("cargo","fmt","-p","proteus-extension","--","--check")
        raw=go("cargo","test","--release","--locked","--offline","--no-fail-fast","-j1","-p","proteus-extension",*SCOPE)
        tests=[tuple(map(int,x)) for x in re.findall(
            rb"^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;",raw,re.M)]
        expected=[4,4,11,64,1] if cumulative else [3,4,10,60,1]
        expected[-2]+=(arm=="candidate")
        assert tests==[(n,0,0,0,0) for n in expected],tests
        print(tier,arm,"release Context, Mode, Model, SDK unit, SDK doc passes:",*expected,flush=True)
        go("cargo","build","--release","--locked","--offline","-j1",*SCOPE)
        real=ordinary(target,src,env)
        example=src/"sdk/examples/r70_layout_probe.rs"
        assert not example.exists()
        example.parent.mkdir(exist_ok=True)
        shutil.copyfile(HERE/"probe.rs",example)
        go("cargo","build","--release","--locked","--offline","-j1","-p","proteus-extension","--example","r70_layout_probe")
        executable=target/"release/examples/r70_layout_probe"
        wire=go(executable,"wire")
        counts=go(executable,"counts")
        assert all(go(executable,"counts")==counts for _ in range(4))
        captured[arm]=real,wire,counts
    a,b=captured.values()
    assert a[:2]==b[:2]
    check_counts(a[2],b[2])
    print(tier,"synthetic ordered HTTP",a[0][1])
    for name,value in a[0][0].items():
        print(tier,"ordinary",name,len(value.splitlines()),len(value),sha256(value).hexdigest())
    print(tier,"probe outputs",len(a[1].splitlines()),len(a[1]),sha256(a[1]).hexdigest())
    print(tier,"activity: case, leaf bytes, successful alloc/realloc requests, requested bytes, final child capacity")
    for arm,(_,_,counts) in captured.items():
        for line in counts.decode().splitlines():
            print(tier,arm,line)
    assert tree(m150)==M150

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_git",type=Path)
    p.add_argument("m150_source",type=Path)
    p.add_argument("prior_394",type=Path)
    p.add_argument("--target",type=Path,required=True)
    p.add_argument("--lock",type=Path,required=True)
    p.add_argument("--admit-exclusive",action="store_true")
    a=p.parse_args()
    exact=a.m150_source.resolve(strict=True)
    previous=a.prior_394.resolve(strict=True)
    target=a.target.resolve(strict=True)
    assert "CARGO_HOME" in os.environ and target.is_dir()
    assert tree(exact)==M150 and sha256(previous.read_bytes()).hexdigest()==PREVIOUS
    free_source=shutil.disk_usage(HERE).free
    free_target=shutil.disk_usage(target).free
    print("preflight free source, target bytes",free_source,free_target,flush=True)
    if not a.admit_exclusive:
        print("Read-only preflight: compiler not started")
        return
    with a.lock.resolve(strict=True).open("rb") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)>=512*2**20
        with tempfile.TemporaryDirectory(prefix="r70-layout-",dir=HERE) as d:
            path=Path(d)
            for tier in ("base","m150+394"):
                compare(tier,path,target,a.stock_git.resolve(strict=True),exact,previous)

if __name__=="__main__":
    main()
