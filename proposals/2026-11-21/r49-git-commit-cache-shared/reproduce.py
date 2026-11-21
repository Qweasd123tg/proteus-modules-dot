#!/usr/bin/env python3
"""Exact locked Git package tests, process wire/HTTP comparison and allocation counts."""
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess as sp
import sys
import tempfile
import threading
import urllib.parse

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-git"
DIR = Path("packages/git")
PATCH = HERE / "source.patch"
FULL = "b"*40
SHORT = FULL[:7]


def wire(exe, src, env):
    spec = importlib.util.spec_from_file_location("upstream_wire", src / "tests/wire.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    requests = []
    class Api(w.Api):
        def log_message(self, fmt, *args):
            pass
        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            requests.append((parsed.path, query))
            if parsed.path == "/workspace/commit" and query.get("hash") == ["deadbeef"]:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"fixture missing commit"}')
            else:
                super().do_GET()
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Api) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        doc, graph = "Коммит "+SHORT, "Граф коммитов"
        def render(arg):
            return {"type":"render","context":"f","session_dir":"/session","surface":"document",
                    "view":"v","argument":arg}
        def act(name,value,seq):
            return {"type":"action","view":"v","action":name,"value":value,"sequence":seq}
        def close():
            return {"type":"close","view":"v"}
        frames=[
            {"type":"hello","protocol":4,"features":json.loads((src/DIR/"extension.json").read_text())["required_features"],
             "workspace":"/workspace","server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
            render(doc),render(doc),close(),
            render(graph),act("graph_log",{"id":FULL,"event":"select"},7),
            act("detail_file",{"id":"sample.py","event":"select"},8),close(),
            render(doc),render(doc),act("all_commit_files",None,9),close(),
            render("Коммит deadbeef"),close(),render(doc),
            {"type":"event","context":"f","event":"run_settled","session_dir":"/session"},close(),
        ]
        try:
            p=sp.run([exe],input=b"".join(json.dumps(f).encode()+b"\n" for f in frames),
                     cwd=src/DIR,env=env,capture_output=True,check=True,timeout=30)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr, p.stderr
    rows=[json.loads(line) for line in p.stdout.splitlines()]
    views=[x for x in rows if x["type"]=="view"]
    opens=[x for x in rows if x["type"]=="open_document"]
    assert len(opens)==1 and opens[0]["argument"]==doc and opens[0]["preview"]
    def with_id(root,key):
        return next((n for n in w.walk(root) if n.get("id")==key),None)
    def diff(row):
        return with_id(row["root"],"commit-patch")
    docs=[x for x in views if x["title"]=="Commit "+SHORT]
    assert len(docs)==7 and diff(docs[0])==diff(docs[1])==diff(docs[-2])==diff(docs[-1])
    assert diff(docs[0])["patch"]==w.patch() and diff(docs[2])==diff(docs[3])
    assert all(any(n.get("action")=="all_commit_files" for n in w.walk(x["root"])) for x in docs[2:4])
    assert diff(docs[4])==diff(docs[0]) and docs[4]["sequence"]==9
    assert any(x["sequence"]==7 and with_id(x["root"],"commit-detail-files") for x in views)
    assert any("fixture missing commit" in str(x) for x in views)
    assert [(path, q.get("hash"), q.get("path")) for path,q in requests if path.startswith("/workspace/commit")] == [
        ("/workspace/commit",[SHORT],None), ("/workspace/commit/diff",[FULL],["sample.py"]),
        ("/workspace/commit",["deadbeef"],None)]
    assert [q for path,q in requests if path=="/workspace/changes"] == [{"session_dir":["/session"]}]*2
    return p.stdout, requests


def main():
    with tempfile.TemporaryDirectory(prefix="git-history-r49-") as name:
        tmp=Path(name); src=tmp/"src"
        env=dict(os.environ,CARGO_TARGET_DIR=str(Path(os.getenv("R49_EXT_TARGET",tmp/"target")).resolve()),
                 CARGO_INCREMENTAL="0",TZ="UTC")
        sp.run(["git","clone","--shared","--quiet","--no-checkout",str(Path(sys.argv[1]).resolve()),src],check=True)
        def run(*cmd):
            sp.run(cmd,cwd=src,env=env,check=True)
        run("git","checkout","--quiet","--detach",BASE)
        run("git","apply","--index","--check",PATCH)
        outputs, probes, metrics, reads = {}, {}, {}, {}
        for arm in ("stock","candidate"):
            if arm=="candidate":
                run("git","apply","--whitespace=error",PATCH)
                run("git","apply","--reverse","--check",PATCH)
                run("git","diff","--check")
            run("cargo","fmt","--check","-p",PKG)
            for profile in ("debug","release"):
                cmd=["cargo","test","--locked","-p",PKG]+(["--release"] if profile=="release" else [])
                result=sp.run(cmd,cwd=src,env=env,stdout=sp.PIPE,stderr=sp.STDOUT)
                if result.returncode:
                    sys.stderr.buffer.write(result.stdout)
                    result.check_returncode()
                summary=re.findall(rb"^test result: .*",result.stdout,re.M)
                assert len(summary)==1 and b"41 passed; 0 failed; 0 ignored" in summary[0], summary
                print(arm,profile,summary[0].decode(),flush=True)
            run("cargo","build","--locked","--release","-p",PKG)
            exe=Path(env["CARGO_TARGET_DIR"])/"release/git"
            outputs[arm],reads[arm]=wire(exe,src,env)
            main_rs=src/DIR/"src/main.rs"
            original=main_rs.read_text(); assert original.count("fn main() {")==1
            main_rs.write_text(original.replace("fn main() {","#[allow(dead_code)]\nfn process_main() {")
                               +"\n"+(HERE/"probe.rs").read_text())
            run("cargo","build","--locked","--release","-p",PKG)
            probes[arm]=sp.check_output([exe,"wire"],env=env)
            metrics[arm]=sp.check_output([exe,"measure"],env=env)
            assert all(sp.check_output([exe,"measure"],env=env)==metrics[arm] for _ in range(4))
            main_rs.write_text(original)
        assert reads["stock"]==reads["candidate"]
        print("http parity:",json.dumps(reads["stock"],separators=(",",":")))
        for domain, arms in (("process frames",outputs),("synthetic roots",probes)):
            x=arms["stock"]
            assert x==arms["candidate"]
            print(domain,"identical",len(x.splitlines()),"lines",len(x),"bytes SHA256",hashlib.sha256(x).hexdigest())
        print("arm size view files commit_patch_B selected_patch_B output_B alloc_calls requested_B")
        for arm in ("stock","candidate"):
            for line in metrics[arm].decode().splitlines():
                print(arm,line)

if __name__=="__main__":
    main()
