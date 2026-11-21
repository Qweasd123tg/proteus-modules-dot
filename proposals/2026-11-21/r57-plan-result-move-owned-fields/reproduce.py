#!/usr/bin/env python3
"""Compare full PlanTool replies and native allocations in both map-order modes."""
import argparse,hashlib,json,os,re,shutil,statistics,subprocess as sp,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE="9469e3b12529d08b1f4a76882693e2065e842c51"
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("repo",type=Path)
parser.add_argument("--rounds",type=int,default=3)
args=parser.parse_args()
if args.rounds<2:
    parser.error("at least two pairs")
ARMS=("base","candidate")
MAPS=("sorted","ordered")
TEST="r57_probe::whole_plan_tool_allocations"

def build(temp,env):
    for arm in ARMS:
        tree=temp/arm
        sp.run(["git","clone","-q","--shared","--no-checkout",args.repo.resolve(),tree],check=True)
        sp.run(["git","checkout","-q","--detach",BASE],cwd=tree,check=True)
        if arm=="candidate":
            sp.run(["git","apply","--check",HERE/"candidate.patch"],cwd=tree,check=True)
            sp.run(["git","apply",HERE/"candidate.patch"],cwd=tree,check=True)
        crate=tree/"tool/plan-tool/src"
        with (crate/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r57_probe;\n")
        shutil.copyfile(HERE/"probe.rs",crate/"r57_probe.rs")
        for mapping in MAPS:
            (crate/"lib.rs").touch()
            cmd=["cargo","test","--locked","--release","-p","plan-tool","--lib",
                 "--no-run","--message-format=json"]
            if mapping=="ordered":cmd+=["--features","serde_json/preserve_order"]
            proc=sp.run(cmd,cwd=tree,env=env,text=True,stdout=sp.PIPE)
            rows=[json.loads(x) for x in proc.stdout.splitlines()]
            if proc.returncode:
                for row in rows:
                    if row.get("reason")=="compiler-message":
                        print(row["message"].get("rendered",""))
                proc.check_returncode()
            exe,=[r["executable"] for r in rows if r.get("executable") and
                  r["target"]["name"]=="plan_tool"]
            dest=temp/f"{arm}-{mapping}"
            shutil.copy2(exe,dest)
            assert TEST+": test" in sp.check_output([dest,"--list"],text=True)

def dumps(value):
    return json.dumps(value,ensure_ascii=False,separators=(",",":"))

def fixtures():
    statuses=("pending","in_progress","completed")
    def form(label,plan,explanation=None):
        data={"plan":plan}
        if explanation is not None:data["explanation"]=explanation
        return label,dumps({"id":"call-ю","name":"update_plan","args":data}),data,None,False
    def steps(count,long=False):
        return [{"step":f'Inspect "section" {i}\nэтап 🦀'+(" x"*140 if long else ""),
                 "status":statuses[i%3]} for i in range(count)]
    return [
        form("ordinary-six",steps(6),"Changed the scope\t🦀"),
        form("many-300",steps(300,True)),
        form("long-explanation",steps(8),"the detail — "*2048),
        form("empty-plan",[]),
        ("non-string-id",'{"id":42,"args":{"plan":[{"step":"","status":"pending"}]}}',
            {"plan":[{"step":"","status":"pending"}]},None,False),
        ("duplicate-id-and-args",'{"id":"prior","args":null,"id":"last","args":{"plan":[]}}',
            {"plan":[]},None,False),
        ("missing-step-and-status",'{"id":"bad","args":{"plan":[{}]}}',None,"missing field `step`",False),
        ("unknown-step-field",'{"id":"bad","args":{"plan":[{"step":"a","status":"pending","unknown":true}]}}',
            None,"unknown field `unknown`",False),
        ("unknown-status",'{"id":"bad","args":{"plan":[{"step":"a","status":"new"}]}}',
            None,"unknown variant `new`",False),
        ("non-object-envelope",'[]',None,"invalid type",False),
        ("broken-call-json",'{',None,"invalid ToolCall JSON",False),
        ("bad-context-first",'{',None,"invalid",True),
    ]

def examine(label,raw,data,error,bad,mapping):
    if label=="broken-call-json" or bad:
        assert raw.startswith(b"ERROR: "),raw
        if bad:
            assert b"invalid ToolCall JSON" not in raw
        else:
            assert error.encode() in raw,raw
        return
    obj=json.loads(raw)
    if error:
        assert obj["ok"] is False and error in obj["error"],obj
        return
    assert obj["ok"] is True and obj["output"]=="Plan updated",obj
    status=[step["status"] for step in data["plan"]]
    assert obj["metadata"]=={
        "plan": data["plan"],"explanation":data.get("explanation"),
        "completed":status.count("completed"),"in_progress":status.count("in_progress"),
        "pending":status.count("pending"),
    },obj
    assert obj["call_id"]=={"non-string-id":"","duplicate-id-and-args":"last"}.get(label,"call-ю")
    if mapping=="ordered":
        assert tuple(obj)==("call_id","ok","output","content","error","metadata")
        assert tuple(obj["metadata"])==("plan","explanation","completed","in_progress","pending")
        assert all(tuple(item)==("step","status") for item in obj["metadata"]["plan"])
    else:
        assert list(obj)==sorted(obj)
        assert list(obj["metadata"])==sorted(obj["metadata"])
        assert all(tuple(item)==("status","step") for item in obj["metadata"]["plan"])

with tempfile.TemporaryDirectory(prefix="r57-plan-tool-") as d:
    temp=Path(d)
    env={**os.environ,"CARGO_TARGET_DIR":str(Path(os.getenv("CARGO_TARGET_DIR",temp/"target")).resolve()),
        "LC_ALL":"C","CARGO_BUILD_JOBS":"1"}
    env.pop("R57_BAD_CONTEXT",None)
    build(temp,env)
    for mapping in MAPS:
        for label,call,data,error,bad in fixtures():
            request=temp/"call.json"
            out=temp/"reply"
            request.write_text(call)
            invocation={**env,"R57_CALL":str(request),"R57_OUT":str(out)}
            if bad:invocation["R57_BAD_CONTEXT"]="1"
            reference=None
            stats={arm:[] for arm in ARMS}
            for lap in range(args.rounds):
                for arm in (ARMS if lap%2==0 else ARMS[::-1]):
                    log=sp.check_output([temp/f"{arm}-{mapping}",TEST,"--exact","--nocapture","--test-threads=1"],
                                        env=invocation,text=True)
                    raw=out.read_bytes()
                    if reference is None:
                        reference=raw
                        examine(label,reference,data,error,bad,mapping)
                    assert raw==reference,(mapping,label,lap,arm)
                    meter=re.search(r"R57 (\d+) (\d+) (\d+)",log)
                    assert meter,log
                    stats[arm].append(tuple(map(int,meter.groups())))
            print(f"{mapping}/{label}: byte-exact; SHA256 {hashlib.sha256(reference).hexdigest()}")
            for arm in ARMS:
                vals=stats[arm]
                print(f" {arm}: requested bytes / allocation calls / logical live peak {vals}; "
                    f"median {tuple(statistics.median(x) for x in zip(*vals))}")
