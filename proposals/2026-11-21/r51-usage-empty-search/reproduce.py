#!/usr/bin/env python3
"""Baseline/candidate wire parity and allocator measurement for Usage."""
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
PKG = "extension-usage"
DIR = Path("packages/usage")
PATCH = HERE/"source.patch"


def wire(exe, src, env):
    spec = importlib.util.spec_from_file_location("upstream_wire",src/"tests/wire.py")
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    initial=w.usage()["requests"][0]
    data=w.usage()
    data["latest_turn_id"]="turn-2"
    data["requests"]=[dict(initial,exchange_id=f"REQ-{i}",turn_id=f"turn-{i%3}",
        model={"provider":"Пример","model":"İstanbul"} if i%3==0 else initial["model"],
        usage=None if i%4==0 else initial["usage"],
        status="error" if i%5==0 else "completed",started_at_ms=i*1000,finished_at_ms=i*1000+500)
        for i in range(67)]
    w.usage=lambda: data
    class Api(w.Api):
        def log_message(self, fmt, *args):
            pass
    with http.server.ThreadingHTTPServer(("127.0.0.1",0), Api) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        frames=[
            {"type":"hello","protocol":4,"features":["surfaces.preview.v1"], "workspace":"/workspace",
             "server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
            {"type":"render","view":"usage","surface":"page","session_dir":"/session","context":"fixture"},
        ]
        for sequence,(action,value) in enumerate([
            ("query"," \t\u2003"),("status","problems"),("status","missing"),("status","all"),
            ("query","REQ TURN-0 İSTANBUL пример"),("order","tokens"),("query","unMATCHed"),
            ("query",""),("order","newest"),("page",1),("period","latest"),("query","FIXTURE"),("query",""),
        ],1):
            frames.append({"type":"action","view":"usage","action":action,"value":value,"sequence":sequence})
        frames.append({"type":"close","view":"usage"})
        try:
            p=sp.run([exe],input=b"".join(json.dumps(f).encode()+b"\n" for f in frames),
                     cwd=src/DIR,env=env,capture_output=True,check=True,timeout=20)
        finally:
            server.shutdown()
            thread.join()
    assert not p.stderr,p.stderr
    rows=[json.loads(line) for line in p.stdout.splitlines()]
    assert [m["sequence"] for m in rows]==list(range(14))
    assert all(m["type"]=="view" and m["view"]=="usage" for m in rows)
    assert [tuple(item) for item in w.READS]==[("/sessions","/session"),("/usage","/session")]
    def notes(row):
        return [node["text"] for node in w.walk(row["root"]) if node.get("type")=="text"]
    assert "Запросы: 67 из 67" in notes(rows[0]) and "Запросы: 67 из 67" in notes(rows[1])
    assert "Запросы: 23 из 67" in notes(rows[5])
    assert "По этим фильтрам запросов нет." in notes(rows[7])
    assert "2 / 4" in notes(rows[10])
    return p.stdout,w.READS


def main():
    with tempfile.TemporaryDirectory(prefix="r51-usage-") as name:
        tmp=Path(name)
        outputs, probes, metrics, reads = {}, {}, {}, {}
        for arm,expected in (("stock",12),("candidate",13)):
            src=tmp/arm
            target=Path(os.getenv("R51_EXT_TARGET_DIR",str(tmp/"targets"))).resolve()/arm
            env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_INCREMENTAL="0",TZ="UTC",PYTHONDONTWRITEBYTECODE="1")
            sp.run(["git","clone","--shared","--quiet","--no-checkout",str(Path(sys.argv[1]).resolve()),src],check=True)
            def run(*cmd):
                sp.run(cmd,cwd=src,env=env,check=True)
            run("git","checkout","--quiet","--detach",BASE)
            run("git","apply","--index","--check",PATCH)
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
                assert len(summary)==1 and f"{expected} passed; 0 failed; 0 ignored".encode() in summary[0], summary
                print(arm,profile,summary[0].decode(),flush=True)
            run("cargo","build","--locked","--release","-p",PKG)
            exe=target/"release/usage"
            outputs[arm],reads[arm]=wire(exe,src,env)
            main_rs=src/DIR/"src/main.rs"
            original=main_rs.read_text()
            assert original.count("fn main() {")==1
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
        print("arm requests case selected filter_calls filter_bytes page_calls page_bytes output_B")
        for arm in ("stock","candidate"):
            for line in metrics[arm].decode().splitlines():
                print(arm,line)

if __name__=="__main__":
    main()
