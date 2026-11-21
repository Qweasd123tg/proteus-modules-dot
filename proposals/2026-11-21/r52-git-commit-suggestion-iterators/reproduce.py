#!/usr/bin/env python3
"""Compare exact Git package, real stdin panel wire, suggestion matrix and scoped allocator requests."""
import hashlib, http.server, importlib.util, json, os, re, subprocess as sp, sys, tempfile, threading
from pathlib import Path

BASE="892f627570369ed60d7205eb0d351c753ec4305f"
HERE=Path(__file__).resolve().parent
PKG="extension-git"
def digest(data):
    return hashlib.sha256(data).hexdigest()

def wire(exe, src, env):
    spec=importlib.util.spec_from_file_location("wire", src/"tests/wire.py")
    w=importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
    template=w.changes()
    class Api(w.Api):
        def log_message(self, *args): pass
    out=[]; reads=[]
    for shape,placeholder,disabled in [
        ("staged","Обновить moved.py",False),("two-staged","Введите сообщение коммита",True),
        ("tracked","Обновить sample.py",False),("conflict","Введите сообщение коммита",True)]:
        fixture=json.loads(json.dumps(template)); entries=fixture["entries"]
        if shape=="two-staged": entries[0]["staged"]="modified"
        if shape=="tracked": entries.pop()
        if shape=="conflict": entries.append({"path":"conflict","status":"conflict","unstaged":"conflict"})
        w.changes=lambda:fixture
        w.READS.clear()
        with http.server.ThreadingHTTPServer(("127.0.0.1",0),Api) as server:
            t=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.025},daemon=True); t.start()
            try:
                frames=[{"type":"hello","protocol":4,"features":json.loads((src/"packages/git/extension.json").read_text())["required_features"],
                         "workspace":"/git-panel-fixture","server":{"origin":f"http://127.0.0.1:{server.server_port}","token":"fixture"}},
                        {"type":"render","surface":"panel","view":"p","context":"f","session_dir":"/session"}]
                for seq,(action,value) in enumerate([("message","   "),("message","Текст"),("toggle_editor",None),("toggle_editor",None),("message","")],1):
                    frames.append({"type":"action","view":"p","action":action,"value":value,"sequence":seq})
                frames.append({"type":"close","view":"p"})
                p=sp.run([exe],input=b"".join(json.dumps(x).encode()+b"\n" for x in frames),cwd=src/"packages/git",env=env,capture_output=True,check=True,timeout=25)
            finally: server.shutdown(); t.join()
        assert not p.stderr,p.stderr
        rows=list(map(json.loads,p.stdout.splitlines()))
        assert len(rows)==6 and [r["sequence"] for r in rows]==list(range(6))
        for i,r in enumerate(rows):
            assert r["type"]=="view" and r["view"]=="p"
            nodes=list(w.walk(r["root"])); inputs=[n for n in nodes if n.get("id")=="message"]
            assert (not inputs) if i==3 else inputs[0]["placeholder"]==placeholder
            button=next(n for n in nodes if n.get("action")=="commit")
            expect=shape=="conflict" or (disabled if i in [0,5] else i==1)
            assert button["disabled"]==expect,(i,shape,button)
        expected_routes = ("changes", "branches", "log")
        assert [(route.split("/"), session) for route, session in w.READS] == [
            (["", "workspace", name], "/session") for name in expected_routes
        ], w.READS
        out.extend(p.stdout.splitlines(keepends=True)); reads.append(list(w.READS))
    return b"".join(out),reads

def main():
    with tempfile.TemporaryDirectory(prefix="git-suggestion-") as name:
        tmp=Path(name); arms={}
        for arm,num in [("stock",41),("candidate",42)]:
            src=tmp/arm
            target=Path(os.environ.get("R52_GIT_TARGETS",tmp/"targets")).resolve()/arm
            env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_INCREMENTAL="0",TZ="UTC")
            sp.run(["git","clone","-q","--no-checkout",str(Path(sys.argv[1]).resolve()),src],check=True)
            def run(*cmd): return sp.run(cmd,cwd=src,env=env,capture_output=True,check=True)
            run("git","checkout","-q","--detach",BASE)
            assert run("git","rev-parse","HEAD").stdout.decode().strip()==BASE
            run("git","apply","--index","--check",HERE/"source.patch")
            if arm=="candidate":
                run("git","apply","--whitespace=error",HERE/"source.patch")
                run("git","apply","--reverse","--check",HERE/"source.patch"); run("git","diff","--check")
            run("cargo","fmt","--check","-p",PKG)
            for profile,flags in [("debug",[]),("release",["--release"])]:
                out=run("cargo","test","--locked","-p",PKG,*flags).stdout.decode()
                summary=next(l for l in out.splitlines() if l.startswith("test result:"))
                assert f"ok. {num} passed; 0 failed;" in summary,summary
                print(arm,profile,summary,flush=True)
            run("cargo","build","--release","--locked","-p",PKG)
            exe=target/"release/git"
            frames,reads=wire(exe,src,env)
            rs=src/"packages/git/src/main.rs"; mainfn="fn main() {\n    run(Git::default());\n}"
            s=rs.read_text(); assert s.count(mainfn)==1
            rs.write_text(s.replace(mainfn,(HERE/"probe.rs").read_text()))
            panel=src/"packages/git/src/panel.rs"
            with panel.open("a") as f:
                f.write("\nimpl Git { pub fn probe_editor(&self, changes: &Value, entries: &[Value]) -> Value { self.commit_editor(changes,entries) } }\n")
            run("cargo","build","--release","--locked","-p",PKG)
            matrix=run(exe,"matrix").stdout; assert len(matrix.splitlines())==2801
            counts=run(exe,"counts").stdout
            assert all(run(exe,"counts").stdout==counts for _ in range(4))
            arms[arm]=(frames,reads,matrix,counts)
        a,b=arms.values()
        assert a[:3]==b[:3]
        for label,raw in [("ordinary panel frames",a[0]),("suggestion matrix",a[2])]:
            print(label,len(raw.splitlines()),len(raw),digest(raw))
        print("ordered workspace API reads per scenario",[(route.rsplit("/",1)[1], session) for route, session in a[1][0]])
        print("allocator calls and requested bytes per invocation, five deterministic runs")
        for arm in arms:
            for line in arms[arm][3].decode().splitlines(): print(arm,line)
if __name__=="__main__": main()
