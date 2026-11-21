#!/usr/bin/env python3
"""Build context-pack on exact stock and compare full JSON builder calls."""
import argparse, hashlib, json, os, re, shutil, statistics, subprocess as sp, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("repo", type=Path)
parser.add_argument("--rounds", type=int, default=9)
args = parser.parse_args()
if args.rounds < 3:
    parser.error("at least three pairs")
ARMS = ("base", "candidate")

def build(temp, env):
    for arm in ARMS:
        tree = temp/arm
        sp.run(["git","clone","-q","--shared","--no-checkout",args.repo.resolve(),tree],check=True)
        sp.run(["git","checkout","-q","--detach",BASE],cwd=tree,check=True)
        if arm == "candidate":
            sp.run(["git","apply","--check",HERE/"candidate.patch"],cwd=tree,check=True)
            sp.run(["git","apply",HERE/"candidate.patch"],cwd=tree,check=True)
        crate=tree/"context/context-pack/src"
        with (crate/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r53_probe;\n")
        for mode in ("meter","clock"):
            probe=(HERE/"probe.rs").read_text()
            if mode=="clock":
                probe=probe.replace("#[global_allocator]","#[allow(dead_code)]")
            (crate/"r53_probe.rs").write_text(probe)
            (crate/"lib.rs").touch()
            cmd=["cargo","test","--locked","--release","-p","context-pack","--lib",
                 "--no-run","--message-format=json"]
            proc=sp.run(cmd,cwd=tree,env=env,text=True,stdout=sp.PIPE)
            rows=[json.loads(x) for x in proc.stdout.splitlines()]
            if proc.returncode:
                for row in rows:
                    if row.get("reason")=="compiler-message":
                        print(row["message"].get("rendered",""))
                proc.check_returncode()
            exe,=[row["executable"] for row in rows if row.get("executable") and
                  row["target"]["name"]=="context_pack"]
            target_exe=temp/f"{arm}-{mode}"
            shutil.copy2(exe,target_exe)
            tests=sp.check_output([target_exe,"--list"],text=True)
            if "r53_probe::context_build_invocation: test" not in tests:
                raise RuntimeError("probe binary is stale; use a non-shared writable CARGO_TARGET_DIR")

def encode(s):
    return json.dumps(s,ensure_ascii=False,separators=(",",":"))

def chunk(source, text, index, metadata, score=None, path=None):
    return {"source":source, "content":f"{text} {index}🙂",
        "render_mode":"source_annotated","score":score,
        "path":path,"metadata":metadata}

def rich_meta(i):
    return {"line":i+1,"source_detail":{"repo":"fixture",
        "ranges":[{"label":"локальный фрагмент-"+"p"*18,"start":j*2,"stop":j*2+1} for j in range(12)],
        "tags":[f"symbol-{j:02d}-"+"q"*12 for j in range(8)]},
        "context_profile":"before","query":"stale"}

def fixtures():
    hm=[chunk("memory:fact","note",i,rich_meta(i)) for i in range(5)]
    hs=[chunk("rg","matched",i,rich_meta(i),path=f"src/item{i}.rs") for i in range(40)]
    he=[chunk("ext","documented",i,rich_meta(i)) for i in range(50)]
    lm=[chunk("memory:fact","short",i,None) for i in range(5)]
    ls=[chunk("rg","short match",i,{"line":i+1},path=f"src/item{i}.rs") for i in range(20)]
    entry=lambda name,b,c,p,n,loops,e=None: (name,{"builder":b,"config":c,"providers":p},n,loops,e)
    def config(*providers,**opts):
        return {"providers":list(providers),"memory_provider":"mem","search_provider":"rg",
                "max_search_results":40,**opts}
    return [
      entry("codex-rich","codex",config("memory","search","external"),
            {"mem":encode(hm),"rg":encode(hs),"external":encode(he)},95,10),
      entry("codex-typical","codex",config("memory","search"),
            {"mem":encode(lm),"rg":encode(ls)},25,75),
      entry("repo-search","repo",config("search"),{"rg":encode(hs)},41,18),
      entry("external-mixed-types","codex",config("external"),{"external":encode([
            chunk("repo_aware:ext","number",0,41),
            chunk("external","array",1,["a",None]),
            chunk("external","object",2,{"context_profile":"before","key":{"v":"🌱"}}),
            chunk("external","null",3,None)])},4,1),
      entry("search-backend-error","codex",config("search"),
            {"rg":"ERROR: synthetic provider error"},1,1),
      entry("memory-backend-error","repo",config("memory"),
            {"mem":"ERROR: synthetic provider error"},None,1,"synthetic provider error"),
      entry("external-bad-json","codex",config("external"),
            {"external":"{"},None,1,"expected a sequence"),
      entry("tight-budget","codex",config("search",max_context_bytes=40),
            {"rg":encode(hs)},3,1),
    ]

def verify(label,raw,fixture,count,failure):
    obj=json.loads(raw)
    if failure:
        assert obj["wire"].startswith("ERROR: ") and failure in obj["wire"],obj
    else:
        assert not obj["wire"].startswith("ERROR: "),obj
        chunks=json.loads(obj["wire"])["chunks"]
        assert len(chunks)==count,(label,len(chunks),count)
        if fixture["builder"]=="codex":
            assert all(c["metadata"]["context_profile"]=="codex_context" for c in chunks)
        if label=="codex-rich":
            assert chunks[0]["metadata"]["provider"]=="memory"
            assert chunks[5]["metadata"]["query"]=="needle"
            assert chunks[-1]["metadata"]["source_detail"]==rich_meta(49)["source_detail"]
        if label=="search-backend-error":
            assert "Workspace search was skipped: synthetic provider error" in chunks[0]["content"]
        if label=="external-mixed-types":
            assert chunks[0]["source"]=="codex_context:ext"
            assert chunks[1]["metadata"]=={"context_profile":"codex_context"}
            assert chunks[2]["metadata"]["key"]=={"v":"🌱"}
    providers=[x[0] for x in obj["trace"]]
    aliases={"memory":"mem","search":"rg"}
    assert providers==[aliases.get(name,name) for name in fixture["config"]["providers"]],obj["trace"]
    for pair in obj["trace"]:
        method,wire=pair
        envelope=json.loads(wire)
        assert envelope["provider_id"]==method and envelope["task"]["text"]=="needle"
        if method=="rg":
            assert envelope["metadata"]["text"]=="needle" and envelope["metadata"]["max_results"]==40

with tempfile.TemporaryDirectory(prefix="r53-context-") as d:
    temp=Path(d)
    target=Path(os.getenv("CARGO_TARGET_DIR",temp/"target")).resolve()
    env={**os.environ,"CARGO_TARGET_DIR":str(target),"LC_ALL":"C"}
    build(temp,env)
    for label,fixture,count,loops,failure in fixtures():
        output=temp/"result"
        fixture_path=temp/"fixture.json"
        fixture_path.write_text(encode(fixture))
        invocation={**env,"R53_FIXTURE":str(fixture_path),"R53_OUT":str(output)}
        canon=None
        data={arm:[] for arm in ARMS}
        for mode in ("meter","clock"):
            n=args.rounds if mode=="clock" and loops>1 else 3
            for j in range(n):
                for arm in (ARMS if j%2==0 else ARMS[::-1]):
                    s=sp.check_output([temp/f"{arm}-{mode}","r53_probe::context_build_invocation",
                        "--exact","--nocapture","--test-threads=1"],text=True,
                        env={**invocation,"R53_LOOPS":str(loops if mode=="clock" else 1)})
                    metrics=tuple(map(int,re.search(r"R53 (\d+) (\d+) (\d+) (\d+)",s).groups()))
                    raw=output.read_bytes()
                    if canon is None:
                        canon=raw
                        verify(label,canon,fixture,count,failure)
                    assert raw==canon,(label,mode,j,arm)
                    data[arm].append((mode,metrics))
        print(f"{label}: byte-exact reply and provider requests; SHA256 {hashlib.sha256(canon).hexdigest()}")
        for arm in ARMS:
            met=[row[:3] for mode,row in data[arm] if mode=="meter"]
            clk=[row[3] for mode,row in data[arm] if mode=="clock"]
            print(f" {arm}: requested/calls/peak {met}; raw ns/invoke {clk}; median ns {statistics.median(clk)}")
