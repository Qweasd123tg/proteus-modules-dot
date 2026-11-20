"""Paired, process-cold attach measurement. Synthetic fixtures only; no payloads persisted in results."""
import argparse, asyncio, datetime, hashlib, json, os, pathlib, signal, tempfile, time, uuid
P = pathlib.Path(__file__).resolve().parent
ROOT = P.parents[1]
HEAD = ".storage-cache-" + hashlib.sha256(b"display-view-v1-head").hexdigest() + ".json"
CLI = pathlib.Path(os.environ.get("PROTEUS_PEER_CLI", ROOT/"r24/target-tests/debug/proteus")).resolve(strict=True)
WORKER = pathlib.Path(os.environ.get("PROTEUS_TEST_SESSION_STORAGE_MODULE", ROOT/"r19-root/bin/worker-stock")).resolve(strict=True)
REF = pathlib.Path(os.environ.get("PROTEUS_TEST_REFERENCE_MODULE", ROOT/"r16-cancel/target/debug/proteus-reference-module")).resolve(strict=True)
SDK = pathlib.Path(os.environ.get("PROTEUS_EXAMPLE_MODULES", ROOT/"r24/core/examples/modules")).resolve(strict=True)
def h(b): return hashlib.sha256(b).hexdigest()
def fhash(path):
    with path.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()
def canonical(obj): return json.dumps(obj,sort_keys=True,separators=(",",":")).encode()
def emit(f,row):
    f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
    print(json.dumps(row,sort_keys=True),flush=True)
def tag(o): return o.get("event",{}).get("type",o["type"])
def config(base):
    cfg=base/"configs/config.toml"; cfg.parent.mkdir(); cwd=base/"ws";cwd.mkdir()
    q=lambda v: json.dumps(str(v))
    cfg.write_text(f'''active_provider="fake"
[providers.fake]
provider="fake"
model="fake-tool-model"
[modules]
workflow="parking_probe"
session_storage="jsonl"
policy="allow_all"
[tools]
enabled=[]
[components.test-model]
command={q(REF)}
[components.test-model.exports.model.fake]
[module_config.model.fake]
implementation="fake"
[components.test-policy]
command={q(REF)}
[components.test-policy.exports.policy.allow_all]
[components.test-session-storage]
command={q(WORKER)}
[components.test-session-storage.exports.session_storage.jsonl]
[components.probe-workflow]
command="python3"
args=["-B",{q(P/"fixture_workflow.py")},{q(SDK)}]
[components.probe-workflow.exports.workflow.parking_probe]
''')
    return [str(CLI),"--config",str(cfg),"--cwd",str(cwd)]
async def start(cli,selection):
    return await asyncio.create_subprocess_exec(*cli,*selection,"server","stdio",
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
        limit=64*1024*1024,start_new_session=True)
async def send(p, obj):
    data=canonical(obj)+b"\n";p.stdin.write(data);await p.stdin.drain();return len(data)
async def frame(p):
    b=await asyncio.wait_for(p.stdout.readline(),timeout=180)
    t=time.perf_counter_ns()
    assert b, f"unexpected end of peer stream, rc {p.returncode}"
    return len(b),t,json.loads(b)
async def request(p, cat, **kw):
    id=str(uuid.uuid4())
    await send(p,dict(type=cat,id=id,**kw))
    while True:
        _,_,o=await frame(p)
        if o["type"]=="response" and o.get("id")==id:
            assert o["ok"], f"{cat} response failed: {o.get('error','')[:180]}"
            return o["output"]
async def clean(p):
    if p.returncode is None:
        await send(p,dict(type="shutdown",id="stop"))
        while await asyncio.wait_for(p.stdout.readline(), timeout=20): pass
        assert await asyncio.wait_for(p.wait(),timeout=10)==0
def emergency(p):
    if p.returncode is None:
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
async def seed(cli,rows,width):
    p=await start(cli,["--parkable-child","--new-session","--parent-session-id",str(uuid.uuid4())])
    try:
        for text in [*[f"archive {min(350,rows-x)} {width}" for x in range(0,rows,350)],"compact"]:
            await request(p,"send",text=text,images=[],options={})
        out=await request(p,"child_session_checkpoint")
        await clean(p)
        return out
    finally: emergency(p)
async def attach(cli,cp):
    ident=str(uuid.uuid4())
    t0=time.perf_counter_ns()
    p=await start(cli,["--resume-session",cp["session"]["session_dir"],"--resume-child-checkpoint",json.dumps(cp,separators=(",",":"))])
    try:
        reqbytes=await send(p,dict(type="child_session_checkpoint",id=ident))
        order=[]; ibytes=0; stats={}; snap=None; proof=None
        while snap is None or proof is None:
            size,t,obj=await frame(p)
            kind=tag(obj);ibytes+=size;order.append(kind)
            m={"ordinal":len(order),"wire_bytes":size,"cumulative_stdout_bytes":ibytes,"arrival_ms":round((t-t0)/1e6,3)}
            if kind=="session_snapshot" and snap is None:
                s=obj["event"]["snapshot"]
                assert s["session_id"]==cp["session"]["session_id"]
                snap=s
                before=(s.get("history") or {}).get("before",0)
                stats["snapshot"]=dict(m,rows=len(s["transcript"]),older_rows=before)
            if kind=="response" and obj.get("id")==ident:
                assert obj["ok"], f"empty/failed cold proof: {obj.get('error','')[:140]}"
                proof=obj["output"];assert proof["checkpoint"]==cp
                stats["ready"]=m
        await clean(p)
        return dict(stats,order=order,request_bytes=reqbytes),proof["root_thread_id"]
    finally: emergency(p)
def journal_stats(j):
    compact=False; last=None; ct=0; archive_message_count=0;active=None
    for line in j.open("rb"):
        r=json.loads(line);ct+=1;last=r["kind"]
        if last=="history_mutated":
            value=r["payload"]
            # This probe batches under the stock worker’s 256-KiB inline threshold.
            if value.get("storage")=="inline": value=value["value"]
            assert "messages" in value, ("inline fixture expected; reduce width",list(value))
            n=len(value["messages"]);mut=value["mutation"]
            archive_message_count=max(archive_message_count,n)
            active=(0 if active is None else active)+n if mut=="append" else n
            if mut=="replace" and (value.get("compaction") or {}).get("changed"): compact=True
    assert compact and last=="turn_settled" and active==2, (ct,last,active,compact)
    return dict(records=ct,active_history_rows=active,largest_mutation_rows=archive_message_count)
async def main(a):
    out=a.output.resolve()
    probes=[("short",12,32),("moderate",a.rows,a.width)] if a.shape=="both" else [(a.shape,12 if a.shape=="short" else a.rows,32 if a.shape=="short" else a.width)]
    with out.open("x",encoding="utf-8") as f:
        emit(f,dict(record="manifest",utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),cli_sha256=fhash(CLI),worker_sha256=fhash(WORKER),reference_sha256=fhash(REF),profile="R24 patched debug CLI; real stock JSONL; local synthetic workflow; fresh peer, OS caches uncontrolled"))
        for name,n,width in probes:
            with tempfile.TemporaryDirectory(dir=P,prefix="temp-") as tmp:
                base=pathlib.Path(tmp);cli=config(base);cpout=await seed(cli,n,width);cp=cpout["checkpoint"]
                d=pathlib.Path(cp["session"]["session_dir"]);j=d/"journal.jsonl"
                assert d.resolve().is_relative_to(base) and d.resolve()==d
                origin=fhash(j); jsize=j.stat().st_size; assert jsize<50_000_000
                jstats=journal_stats(j)
                saved=d/HEAD
                # Force one (unmeasured) cache miss and verify the stock process published a matching head.
                if saved.exists(): saved.rename(base/"initial-head")
                warm,root=await attach(cli,cp)
                assert root!=cpout["root_thread_id"]
                hd=json.loads(saved.read_bytes())
                assert hd["source"]["revision"]==cp["revision"]
                hv=hd["value"]; assert hv["source"]["snapshot"]["revision"]==cp["revision"]
                assert hd["source"]["content_sha256"]==hv["source"]["snapshot"]["content_sha256"]
                original_head=saved.read_bytes()
                def stamp():
                    s=j.stat(); return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
                original_stamp=stamp()
                assert fhash(j)==origin
                emit(f,dict(record="fixture",shape=name,rows_seeded=n,width=width,journal_bytes=jsize,journal_sha256=origin,
                     checkpoint_sha256=h(canonical(cp)),dir_token=h(str(d).encode()),head_sha256=h(original_head),journal_stamp_sha256=h(canonical(original_stamp)),warmup=warm,**jstats))
                processes={cpout["root_thread_id"],root}
                for i in range(a.reps):
                    for arm in (["present","missing"] if i%2==0 else ["missing","present"]):
                        # Never replace the session/journal or touch other storage files: keep inode and ctime stable.
                        if arm=="missing":
                            if saved.exists(): saved.rename(base/f"withheld-{i}")
                        elif not saved.exists() or saved.read_bytes()!=original_head:
                            swap=base/f"restore-{i}";swap.write_bytes(original_head);swap.replace(saved)
                        assert stamp()==original_stamp and (saved.is_file()==(arm=="present")) and fhash(j)==origin
                        if arm=="present": assert saved.read_bytes()==original_head
                        data,physical=await attach(cli,cp)
                        assert physical not in processes;processes.add(physical)
                        assert stamp()==original_stamp and fhash(j)==origin and (not saved.exists() or json.loads(saved.read_bytes())["source"]["revision"]==cp["revision"])
                        emit(f,dict(record="sample",shape=name,round=i+1,head=arm,verified_exact_checkpoint=True,journal_unchanged=True,inode_and_stat_unchanged=True,**data))
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--output",type=pathlib.Path,required=True)
    ap.add_argument("--shape",choices=["short","moderate","confirmation","both"],default="both");ap.add_argument("--rows",type=int,default=1000);ap.add_argument("--width",type=int,default=175);ap.add_argument("--reps",type=int,default=2)
    asyncio.run(main(ap.parse_args()))
