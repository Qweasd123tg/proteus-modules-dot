#!/usr/bin/env python3
"""Stock explicit-open HTTP server + one real JSONL process under an isolated temporary root."""
import argparse,hashlib,json,os,selectors,signal,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from rpc import Fixture,Worker,msg,uid
now=time.monotonic_ns
IX=".storage-catalog-v1.json"
def seed(exe,root,cwd,sid,rows):
    w=Worker(exe,"jsonl")
    try:
        a=Fixture.__new__(Fixture);a.w=w
        desc=w.do("create",config_root=str(root),workspace_path=str(cwd),session_id=sid,parent_session_id=None)["descriptor"]
        a.session=desc["session"];a.acquire(); tail=[]
        for start in range(0,rows,100):
            chunk=[]
            for i in range(start,min(start+100,rows)):
                v=msg(i,f"synthetic-{i:06d}: "+"Фиктивная строка журнала. "*3)
                v["parts"][0]["part_id"]=uid(1000000+i)
                if i%2:v["role"]="Assistant";v["parts"][0]["provenance"]="model"
                chunk.append(v)
            a.write(chunk);tail=(tail+chunk)[-100:]
        if rows>100:a.write(tail,"replace",dict(changed=True,user_message_replacements=[],reason="Synthetic tail",input_messages=rows,output_messages=100,summary_source="synthetic-r16",metadata=None))
        a.release()
        d=Path(desc["local_path"]);assert d.is_relative_to(root);return d
    finally:w.close()
def canon(paths):
    return [{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (d/"journal.jsonl",d/"session.json")} for d in paths]
def brief(tree):
    q=tree.sample()
    assert not q["memory_incomplete_pids"]
    return {k:q[k] for k in ("pss_kib","rss_kib","private_kib","swap_pss_kib","process_count")}
def proc(pid):
    base=Path("/proc")/str(pid)
    data={k:int(v) for line in (base/"io").read_text().splitlines() for k,v in [line.split(": ")]}
    raw=(base/"stat").read_text().rsplit(")",1)[1].split()
    return {**{k:data[k] for k in ("rchar","wchar","read_bytes","write_bytes")},"cpu_ticks":int(raw[11])+int(raw[12])}
def measured(pid,fn):
    a=proc(pid);t=now();resp=fn();ms=round((now()-t)/1e6,3);b=proc(pid)
    return resp,{"ms":ms,**{k:b[k]-v for k,v in a.items()}}
def scoped(expected,entries,key):
    ids=[key(e) for e in entries];assert len(ids)==len(expected) and set(ids)==set(expected),(len(ids),len(expected))
def main():
    ap=argparse.ArgumentParser()
    for k in ("core","reference","worker","source","out"):ap.add_argument("--"+k,type=Path,required=True)
    ap.add_argument("--archives",type=int,required=True);ap.add_argument("--rows",type=int,default=2000);args=ap.parse_args()
    for k in ("core","reference","worker","source"):setattr(args,k,getattr(args,k).resolve(strict=True))
    assert 0<=args.archives<=100 and 100<=args.rows<=125000
    sys.path.insert(0,str(args.source/"examples/performance/history-scale"));from fixtures import profile
    sys.path.insert(0,str(args.source/"examples/performance/common"));from proc_sampler import Tree
    out=args.out.resolve();out.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="r17-synthetic-") as tmp:
        home=Path(tmp);root=home/"config";cwd=home/"work";root.mkdir();cwd.mkdir()
        ids=[uid(7)]+[uid(100+i) for i in range(args.archives)]
        paths=[seed(args.worker,root,cwd,s,100 if j==0 else args.rows) for j,s in enumerate(ids)]
        hashes=canon(paths);closed=paths[1:];active=paths[0];idx=lambda:sum((p/IX).exists() for p in closed)
        assert idx()==0, "unexpected fixture generation"
        sizes=sorted({(p/"journal.jsonl").stat().st_size for p in closed});records=sorted({(p/"journal.jsonl").read_bytes().count(b"\n") for p in closed})
        conf=profile(args.reference,0).replace('[modules]\n','[modules]\nsession_storage="jsonl"\n')+'\n[components.store]\ncommand='+json.dumps(str(args.worker))+'\n[components.store.exports.session_storage.jsonl]\n[components.store.transport]\nmax_frame_bytes=134217728\n'
        config=root/"config.toml";config.write_text(conf)
        results=dict(archives=args.archives,rows_per_archive=args.rows,active_rows=100,model_tail=100,closed_journal_size_variants=sizes,closed_record_count_variants=records,closed_journal_bytes_total=sum((d/"journal.jsonl").stat().st_size for d in closed),clock_ticks_per_second=os.sysconf("SC_CLK_TCK"),worker=[],http=[])
        def direct(label,ops):
            w=Worker(args.worker,"jsonl")
            try:
                for op in ops:
                    command,extra=("list_candidates",{}) if op=="candidates" else ("list",{"audit":op=="audit"})
                    before=idx()
                    rsp,m=measured(w.process.pid, lambda:w.do(command,config_root=str(root),workspace_path=str(cwd),**extra))
                    if op=="candidates":
                        scoped(ids,rsp["sessions"],lambda x:x["session"]["session_id"])
                    else:
                        scoped(ids,rsp["sessions"],lambda x:x["descriptor"]["session"]["session_id"])
                        assert all(x["message_count"]==100 and x["preview"] for x in rsp["sessions"])
                    results["worker"].append(dict(label=label,op=op,closed_index_before=before,closed_index_after=idx(),**m))
            finally:w.close()
        direct("pre_http_fresh_process",["candidates"]);assert idx()==0
        def server(label):
            start=now()
            with (out/(label+".log")).open("w") as log:
                p=subprocess.Popen([args.core,"--config",config,"--cwd",cwd,"--resume-session",active,"server","http","--host","127.0.0.1","--port","0","--ready-stdout"],cwd=cwd,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
                try:
                    with selectors.DefaultSelector() as sel:
                        sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(45)
                        ready=json.loads(p.stdout.readline());assert ready["type"]=="http_ready"
                        ready_ms=round((now()-start)/1e6,3);origin=ready["origin"];assert origin.startswith("http://127.0.0.1:")
                    def get(url,body=None):
                        rq=Request(origin+url,data=None if body is None else json.dumps(body).encode(),headers={"Content-Type":"application/json"})
                        with urlopen(rq,timeout=180) as resp:return json.load(resp)
                    assert get("/health")["ok"] and get("/bootstrap")["session_dir"]==str(active)
                    pg=get("/history/page?"+urlencode(dict(session_dir=str(active))));assert pg["total"]==100
                    tree=Tree(p.pid,root_group="backend")
                    sample=tree.sample()
                    wp=[pr["pid"] for pr in sample["processes"] if pr["exe"]==str(args.worker)];assert len(wp)==1,[(pr["exe"],pr["argv"][:1]) for pr in sample["processes"]]
                    snap=dict(label=label,http_ready_ms=ready_ms,ready_tree=brief(tree),calls=[])
                    for key,route in [("global_first","/sessions"),("global_again","/sessions"),("workspace","/sessions/current?"+urlencode(dict(session_dir=str(active))))]:
                        before=idx();resp,m=measured(wp[0],lambda:get(route)); scoped(ids,resp,lambda x:x["session_id"])
                        a=[x["session_id"] for x in resp if x.get("activity") is not None]
                        assert a==[ids[0]],a
                        assert all(x["message_count"]==100 and x["preview"] for x in resp)
                        snap["calls"].append(dict(route=key,closed_index_before=before,closed_index_after=idx(),active_count=len(a),**m))
                    snap["after_tree"]=brief(tree);results["http"].append(snap)
                    assert get("/history/page?"+urlencode(dict(session_dir=str(active))))["total"]==100
                    get("/shutdown",{})
                finally:
                    try:os.killpg(p.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:p.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
                    p.stdout.close()
        server("stock_missing");assert idx()==args.archives
        server("stock_valid");assert idx()==args.archives
        direct("fresh_valid_indices",["candidates","foreground","foreground","audit"])
        # Only the synthetic seed's disposable catalog projections, not journals.
        for d in closed:
            index=d/IX;assert index.is_relative_to(root) and index.is_file();index.rename(d/(IX+".parked"))
        direct("fresh_missing_indices",["candidates","foreground","foreground","audit"])
        assert idx()==args.archives and hashes==canon(paths)
        results["canonical_hashes_unchanged"]=True
        (out/"summary.json").write_text(json.dumps(results,indent=2)+"\n")
        print(json.dumps(results),flush=True)
if __name__=="__main__":main()
