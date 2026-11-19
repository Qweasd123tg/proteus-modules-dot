#!/usr/bin/env python3
"""Send to the already-open A while a genuine unrelated catalog replay remains in flight."""
import shutil,argparse,concurrent.futures,hashlib,json,os,selectors,signal,subprocess,sys,tempfile,threading,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from run import seed,uid,IX,canon
now=time.monotonic_ns
ms=lambda x,y:round((y-x)/1e6,3)
def wait(fn,limit=30):
    t=time.monotonic()+limit
    while time.monotonic()<t:
        a=fn()
        if a:return a
        time.sleep(.001)
    raise TimeoutError()
def main():
    ap=argparse.ArgumentParser()
    for k in ("core","reference","worker","source","out"):ap.add_argument("--"+k,type=Path,required=True)
    ap.add_argument("--archives",type=int,default=100)
    ap.add_argument("--control",type=Path,required=True)
    ap.add_argument("--pairs",type=int,default=2)
    ap.add_argument("--seed-fixture",type=Path,help="Reuse an unmodified synthetic seed/work pair created by this stand")
    args=ap.parse_args(); assert 5<=args.archives<=100
    for k in ("core","reference","source","control"):setattr(args,k,getattr(args,k).resolve(strict=True))
    sys.path.insert(0,str(args.source/"examples/performance/history-scale"));from fixtures import profile
    from journal import records,text
    out=args.out.resolve();out.mkdir(exist_ok=False)
    results=[]
    workers = {"stock":args.control,"candidate":args.worker.absolute()}
    with tempfile.TemporaryDirectory(prefix="r18-catalog-send-") as tmp:
        home=Path(tmp)
        if args.seed_fixture is None:
            seeded=home/"seed";cwd=home/"work";seeded.mkdir();cwd.mkdir()
            a0=seed(args.control,seeded,cwd,uid(7),100)
            closed0=[seed(args.control,seeded,cwd,uid(100+i),2000) for i in range(args.archives)]
        else:
            seeded=args.seed_fixture.resolve()/"seed";cwd=seeded.parent/"work"
            ws,=list((seeded/"sessions").iterdir())
            a0=ws/"0000000007";closed0=[ws/f"{100+i:010d}" for i in range(args.archives)]
            assert cwd.is_dir() and a0.is_dir() and all(d.is_dir() for d in closed0)
            assert sum(1 for d in ws.iterdir() if d.is_dir() and d.name.isdigit())==args.archives+1
        ids=[uid(7)]+[uid(100+i) for i in range(args.archives)]
        print("Seed ready",flush=True)
        modes=[("stock","idle",0),("candidate","idle",0)]
        for i in range(args.pairs):
            modes.extend((v,"overlap",i+1) for v in (["stock","candidate"] if i%2==0 else ["candidate","stock"]))
        for flavor,mode,trial in modes:
            tag=f"{flavor}-{mode}-{trial}"
            args.worker=workers[flavor]
            wait(lambda:args.worker.is_file(),300)
            root=home/tag
            shutil.copytree(seeded,root)
            a=root/a0.relative_to(seeded)
            closed=[root/q.relative_to(seeded) for q in closed0]
            assert not any((p/IX).exists() for p in closed)
            ah=(a/"journal.jsonl").read_bytes();h=canon(closed)
            conf=profile(args.reference,0).replace('[modules]\n','[modules]\nsession_storage="jsonl"\n')+'\n[components.store]\ncommand='+json.dumps(str(args.worker))+'\n[components.store.exports.session_storage.jsonl]\n[components.store.transport]\nmax_frame_bytes=134217728\n'
            config=root/"config.toml";config.write_text(conf)
            with (out/(tag+".log")).open("w") as log:
                p=subprocess.Popen([args.core,"--config",config,"--cwd",cwd,"--resume-session",a,"server","http","--host","127.0.0.1","--port","0","--ready-stdout"],cwd=cwd,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
                try:
                    with selectors.DefaultSelector() as sel:
                        sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(45)
                        ready=json.loads(p.stdout.readline());assert ready["type"]=="http_ready"
                        origin=ready["origin"];assert origin.startswith("http://127.0.0.1:")
                    def get(route,body=None):
                        rq=Request(origin+route,data=None if body is None else json.dumps(body).encode(),headers={"Content-Type":"application/json"})
                        with urlopen(rq,timeout=180) as r:return json.load(r)
                    assert get("/bootstrap")["session_dir"]==str(a)
                    query="?"+urlencode(dict(session_dir=str(a)));assert get("/history/page"+query)["total"]==100
                    mark={};ready_sse=threading.Event()
                    def watch():
                        with urlopen(origin+"/events"+query,timeout=60) as resp:
                            for line in resp:
                                t=now()
                                if not line.startswith(b"data: "):continue
                                e=json.loads(line[6:]).get("event",{});typ=e.get("type")
                                if typ=="session_snapshot":
                                    assert e["snapshot"]["session_id"]==uid(7);ready_sse.set()
                                if typ=="runtime" and e["envelope"]["session_id"]==uid(7):
                                    ev=e["envelope"]["event"]
                                    if isinstance(ev,dict) and ev.get("AssistantTextDelta",{}).get("text"):mark.setdefault("first_text",t)
                                if typ=="turn_output":mark["turn_output"]=t;return
                                if typ=="error":raise RuntimeError(e)
                    def listit():
                        mark["list_start"]=now();j=get("/sessions");mark["list_done"]=now()
                        assert len(j)==len(ids) and set(e["session_id"] for e in j)==set(ids)
                        assert all(e["message_count"]==100 and e["preview"] for e in j if e["session_id"]!=ids[0])
                        assert [x["session_id"] for x in j if x.get("activity") is not None]==[uid(7)]
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                        s=pool.submit(watch);assert ready_sse.wait(15)
                        if mode=="overlap":
                            l=pool.submit(listit)
                            def progress():
                                found=sum((d/IX).is_file() for d in closed)
                                if l.done():raise RuntimeError("missed overlap")
                                return found if 0<found<args.archives else None
                            count=wait(progress);mark["observed_progress"]=now()
                        else:count=0
                        mark["send_start"]=now();acc=get("/send-async",dict(id="catalog-test",session_dir=str(a),text="hello"));mark["ack"]=now()
                        assert acc["ok"] and acc["output"]["accepted"] and acc["output"]["run_id"]=="catalog-test"
                        s.result(timeout=45)
                        if mode=="overlap":
                            l.result(timeout=45);assert mark["list_start"]<mark["observed_progress"]<=mark["send_start"]<mark["list_done"]
                    wait(lambda:get("/history/page"+query)["total"]==102)
                    reqs=[payload["request"] for record,payload in records(a) if record["kind"]=="model_request_recorded"]
                    assert len(reqs)==1
                    msgs=reqs[0]["messages"];seed_msgs=[m for m in msgs if text(m).startswith("synthetic-")]
                    assert len(msgs)==102 and len(seed_msgs)==100 and len([m for m in msgs if text(m)=="hello"])==1
                    assert all(m["id"]==uid(1000+i) and m["parts"][0]["part_id"]==uid(1000000+i) and text(m)==f"synthetic-{i:06d}: "+"Фиктивная строка журнала. "*3 for i,m in enumerate(seed_msgs))
                    assert h==canon(closed) and (a/"journal.jsonl").read_bytes().startswith(ah)
                    if mode=="overlap":assert all((q/IX).is_file() for q in closed)
                    else:assert not any((q/IX).is_file() for q in closed)
                    d=dict(worker=flavor,trial=trial,mode=mode,archives=args.archives,rows_per_archive=2000,index_files_observed_at_trigger=count,accepted_ms=ms(mark["send_start"],mark["ack"]),first_text_ms=ms(mark["send_start"],mark["first_text"]),turn_output_ms=ms(mark["send_start"],mark["turn_output"]),request_count=1,request_length=102,canonical_archives_unchanged=True,marks=mark)
                    if mode=="overlap":d.update(list_ms=ms(mark["list_start"],mark["list_done"]),remaining_list_from_send_ms=ms(mark["send_start"],mark["list_done"]))
                    results.append(d);print(json.dumps(d),flush=True);(out/(tag+".json")).write_text(json.dumps(d,indent=2)+"\n")
                    get("/shutdown",{})
                finally:
                    try:os.killpg(p.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
                    p.stdout.close()
if __name__=="__main__":main()
