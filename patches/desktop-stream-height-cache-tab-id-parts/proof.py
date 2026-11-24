"""Verify a bounded source patch against the pinned Desktop and Core; perform independent offline paired builds."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
sys.dont_write_bytecode=True
from lift import lift
from desktop_inputs import verify_vendor, git_blob

P=Path(__file__).resolve().parent
CHANGED={"crates/tabs/src/identity.rs":"e89b5d9bf7af29f38df6645f89ee6bccf8c1a26d",
         "src/ui/chat/history/height_key.rs":"cad59da682ef5822cd2631c003c11df091e5a152"}
HIST="src/ui/chat/history.rs"
POST580="72083028e592d9f7e981a67e800a6367438251a0"
def run(*args,cwd=None,env=None):
    cmd=list(map(str,args));res=subprocess.run(cmd,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if res.returncode: raise RuntimeError(f"{cmd}:\n{res.stdout}")
    return res.stdout
def check(x,msg):
    if not x: raise ValueError(msg)
def blob(p): return git_blob(p.read_bytes())
def prep(s,nat,pins):
    for f,v in pins.items():
        a=s/f
        check(a.is_file() and not a.is_symlink() and blob(a)==v["git_blob"],f)
        b=nat/f;b.parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(a,b);b.chmod(0o644)
def validate_source(source,root,pins,tc):
    dirs={}
    for variant in ("stock","candidate"):
        native=root/variant/"product";prep(source,native,pins);dirs[variant]=native
    for specs in ((P/"source.patch",P/"composition-580.patch"),(P/"composition-580.patch",P/"source.patch")):
        native=dirs["candidate"]
        for patch in specs:
            run("git","apply","--check",patch,cwd=native);run("git","apply",patch,cwd=native)
        for f,h in {**CHANGED,HIST:POST580}.items(): check(blob(native/f)==h,f)
        for patch in reversed(specs):
            run("git","apply","-R","--check",patch,cwd=native);run("git","apply","-R",patch,cwd=native)
        for f,spec in pins.items(): check(blob(native/f)==spec["git_blob"] and stat.S_IMODE((native/f).stat().st_mode)==0o644,f)
    native=dirs["candidate"]
    stats=run("git","apply","--numstat",P/"source.patch",cwd=native).splitlines()
    check({r.split("\t")[-1] for r in stats}==set(CHANGED),stats)
    run("git","apply","--check",P/"source.patch",cwd=native);run("git","apply",P/"source.patch",cwd=native)
    for f,spec in pins.items():
        check(blob(native/f)==CHANGED.get(f,spec["git_blob"]) and stat.S_IMODE((native/f).stat().st_mode)==0o644,f)
    run(tc/"rustfmt","--check","--edition","2024","--config","skip_children=true",*(native/f for f in CHANGED))
    return dirs
def build(which,native,vendor,tc):
    dest=native.parent/"proof";dest.mkdir()
    shutil.copytree(native/"crates/tabs",dest/"crates/tabs")
    lift(native,P,dest/"src")
    for n in ("Cargo.toml","Cargo.lock"):shutil.copyfile(P/n,dest/n)
    (dest/".cargo").mkdir()
    (dest/".cargo/config.toml").write_text('[source.crates-io]\nreplace-with="pinned-vendor"\n[source.pinned-vendor]\ndirectory='+json.dumps(str(vendor))+'\n')
    env={**os.environ,"PATH":str(tc)+os.pathsep+os.environ["PATH"],"CARGO_HOME":str(dest/"home"),
        "RUSTC":str(tc/"rustc"),"CARGO_TARGET_DIR":str(dest/"target"),"RUSTFLAGS":"","RUSTDOCFLAGS":"","CARGO_BUILD_JOBS":"2","CARGO_INCREMENTAL":"0"}
    data={}
    for profile in ("debug","release"):
        cmd=[tc/"cargo","test","--workspace","--offline","--locked"]
        if profile=="release":cmd+=["--release"]
        out=run(*cmd,"--","--nocapture","--test-threads=1",cwd=dest,env=env)
        (dest/f"{profile}.log").write_text(out)
        cases,routes,public={},{},[]
        for typ,raw in re.findall(r"\b(CASE|ROUTE|PUBLIC) (\{[^\n]*|\[[^\n]*)",out):
            item=json.loads(raw)
            if typ=="CASE":cases[item["case"],item["idx"]]=item
            elif typ=="ROUTE":routes[item["case"]]=item
            else:public.append(item)
        counts=list(map(int,re.findall(r"test result: ok\. (\d+) passed; 0 failed",out)))
        check(len(counts)>=2 and sorted(c for c in counts if c>0)[0]==4 and len([c for c in counts if c>0])==2,counts)
        data[profile]=(cases,routes,public,counts)
        print(f"{which} {profile}: test counts {counts}; {len(cases)} cases, {len(routes)} snapshots",flush=True)
    return data

def compare(a,b):
    (ac,ar,ap,at),(bc,br,bp,bt)=a,b
    check(at==bt and ap==bp and len(ap)==34,"tabs public capacities and allocation parity")
    names={"path","empty_path","relative","unicode","long","codex","codex_empty","codex_long",
           "sha55","sha56","sha63","sha64","sha65","non_utf8"}
    check(set(ac)==set(bc)=={(n,i) for n in names for i in range(4)},"case inventory (Unix proof)")
    tabs={"path":"chat:/synthetic/saved-chat","empty_path":"chat:","relative":"chat:relative//./../a:b/",
          "unicode":"chat:кат/日本/🙂\n","long":"chat:"+"x"*4096,"codex":"codex:opaque::child:\nλ",
          "codex_empty":"codex:","codex_long":"codex:"+":a"*2048,"non_utf8":"chat:"+b"a/\xff:\xe2\x82/\x80\n".decode("utf8","replace")}
    for n in (55,56,63,64,65):tabs[f"sha{n}"]="chat:"+"q"*(n-42)
    def digest(s):return list(hashlib.sha256(s.encode()).digest())
    def paired(x,y,label):
        for k in set(x)|set(y):
            if k not in ("requests","bytes"):check(x[k]==y[k],(label,k))
    direct={}
    for (n,i),x in ac.items():
        y=bc[n,i];paired(x,y,(n,i))
        expected={"identity":digest(tabs[n]+":"+x["id"]),"revision":digest("новая:ревизия\n"),"layout":[0]*32,
                  "prefix":max(i-1,0),"base":None if i==2 else [digest("" if i==3 else "prior:"),max(i-1,0)]}
        check(x["tab"]==tabs[n] and x["key"]==expected,(n,i,"independent preimage/key"))
        check(x["requests"]>y["requests"] and x["bytes"]>y["bytes"],(n,i,x,y))
        check(y["requests"]>0 if n=="non_utf8" else y["requests"]==0,(n,i,"candidate requests"))
        pair=[x["requests"],y["requests"],x["bytes"],y["bytes"]]
        check(direct.setdefault(n,pair)==pair,(n,"unexpected uuid effect"))
    tags={"first","duplicate","stale","foreign-session","foreign-stream","new-revision","reopen","root-reappears","no-cursor","other-accepted"}
    check(set(ar)==set(br)==tags,"route inventory")
    route={}
    for t in sorted(tags):
        x,y=ar[t],br[t];paired(x,y,t)
        if not x["shown"] or t=="no-cursor":
            check((x["requests"],x["bytes"])==(y["requests"],y["bytes"]),t)
        else:
            check(len(x["keys"])==2 and x["keys"][0]==x["keys"][1] and x["keys"][0] is not None,t)
            check(x["requests"]>y["requests"] and x["bytes"]>y["bytes"],t)
        route[t]=[x["requests"],y["requests"],x["bytes"],y["bytes"]]
    return {"native_and_harness_tests":at[:2],"direct":dict(sorted(direct.items())),"event":route,
            "key_cases":len(ac),"public_capacity_cases":len(ap),"event_cases":len(ar)}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ("source","vendor","archives","upstream_lock","toolchain"):parser.add_argument(n,type=lambda x:Path(x).resolve())
    parser.add_argument("--result",type=Path);args=parser.parse_args()
    cv=run(args.toolchain/"rustc","--version").strip()
    check(cv.startswith("rustc 1.95.0 "),cv)
    pins=json.loads((P/"SOURCE-PROVENANCE.json").read_text())["source"]
    audit=verify_vendor(args.upstream_lock,P/"Cargo.lock",args.archives,args.vendor)
    check(audit["archive_count"]==37 and audit["file_count"]==1708,"locked registry closure")
    print(f"{cv}; verified {len(pins)} source blobs, {audit['archive_count']} archives / {audit['file_count']} files",flush=True)
    with tempfile.TemporaryDirectory(prefix="desktop-height-key-") as temp:
        dirs=validate_source(args.source,Path(temp),pins,args.toolchain)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures={k:pool.submit(build,k,v,args.vendor,args.toolchain) for k,v in dirs.items()}
            runs={k:f.result() for k,f in futures.items()}
        result={"compiler":cv,"patch_sha256":hashlib.sha256((P/"source.patch").read_bytes()).hexdigest(),"stock_changed":{f:pins[f]["git_blob"] for f in CHANGED},
                "postimages":CHANGED,"both_order_580":True,"registry_archives":audit["archive_count"],"vendor_files":audit["file_count"],
                "verified_input_blobs":len(pins),"counts_format":"stock requests, candidate requests, stock requested bytes, candidate requested bytes",
                "profiles":{p:compare(runs["stock"][p],runs["candidate"][p]) for p in ("debug","release")}}
        print(json.dumps(result,indent=2))
        if args.result:args.result.write_text(json.dumps(result,indent=2)+"\n")
if __name__=="__main__":main()
