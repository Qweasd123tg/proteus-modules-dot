"""Linux. Pass two actual release proteus-session-storage-module executables (before/after).
JSON-RPC over stdio. Fixture writes and correctness controls are outside measured work."""
import ctypes
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

def uid(i):
    return str(uuid.UUID(int=i))

class Worker:
    def __init__(self, binary):
        self.p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        if "PROTEUS_BENCH_WORKER_CPU" in os.environ:
            os.sched_setaffinity(self.p.pid,{int(os.environ["PROTEUS_BENCH_WORKER_CPU"])})
        self.seq=0
        clock=ctypes.c_int()
        assert ctypes.CDLL(None).clock_getcpuclockid(self.p.pid,ctypes.byref(clock))==0
        self.clock_id=clock.value
        self.frame("initialize", {"protocol_version":"v3","component_id":"storage-test",
            "exports":[{"slot":"session_storage","module_id":"sqlite","contract_version":"v1",
                        "composition":"select_one","module_config":{},"host_features":[]}]})
    def frame(self,method,params,error=False):
        ident=f"h:1:{self.seq}"; self.seq+=1
        self.p.stdin.write(json.dumps(dict(jsonrpc="2.0",id=ident,method=method,params=params),
                                      separators=(",",":")).encode()+b"\n"); self.p.stdin.flush()
        line=self.p.stdout.readline()
        if not line: raise ValueError("worker closed stdout")
        response=json.loads(line)
        assert response["id"]==ident and (("error" in response)==error),response.get("error")
        return response["error" if error else "result"]
    def call(self,operation,*,error=False,**args):
        ident=f"h:1:{self.seq}"
        return self.frame("execute",{"export":{"slot":"session_storage","module_id":"sqlite"},
                         "lineage":{"root_invocation_id":ident,"parent_invocation_id":None,"depth":0},
                         "params":{"operation":operation,**args}},error)
    def cpu_ns(self):
        return time.clock_gettime_ns(self.clock_id)  # Full worker process, including SDK request threads.
    def rss(self):
        return int(next(l for l in Path(f"/proc/{self.p.pid}/status").read_text().splitlines() if l.startswith("VmHWM:")).split()[1])
    def close(self):
        self.p.stdin.close()
        try: self.p.wait(3)
        except subprocess.TimeoutExpired:
            self.p.terminate(); self.p.wait(3)
        self.p.stdout.close()

def seed(binary,d,n,size):
    p=Worker(binary); d.mkdir(); config=d/"config"; work=d/"work"; config.mkdir(); work.mkdir()
    try:
        desc=p.call("create",config_root=str(config),workspace_path=str(work),session_id=uid(42),parent_session_id=None)["descriptor"]
        session=desc["session"]; wr=p.call("acquire_writer",session=session); lease=wr["lease"]; rev=wr["revision"]
        expected=[]
        for i in range(1,n+1):
            pattern='some source code: fn main() { println!("hello"); }\n'
            text=f'{i:08}:'+ (pattern*((size+len(pattern)-1)//len(pattern)))[:size]
            message={"id":uid(20_000+i),"role":"User","phase":None,"parts":[{
                "part_id":uid(40_000+i),"provenance":"user","scope":"conversation","payload":{"Text":{"text":text}}}],
                "name":None,"tool_call_id":None,"metadata":None}
            entry={"kind":"history_mutated","payload":{"previous_revision":i-1,"new_revision":i,"mutation":"append",
                    "messages":[message],"compaction":None,"tool_results":[]}}
            attribution={"execution_id":None,"thread_id":uid(222_222),"turn_id":None}
            ack=p.call("commit",commit={"lease":lease,"operation_id":uid(i),"expected":rev,"timestamp_ms":1234,
                                      "attribution":attribution,"entry":entry})["ack"]
            assert ack["record"]["entry"]==entry and ack["record"]["session_seq"]==i
            expected.append(ack["record"]); rev=ack["revision"]
        p.call("release_writer",lease=lease)
    finally: p.close()
    dbpath=Path(desc["record_location"])
    assert dbpath.is_file()
    with sqlite3.connect(f"file:{dbpath}?mode=ro",uri=True) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        assert db.execute("SELECT COUNT(*) FROM journal").fetchone()==(n,)
    return session,expected

def exercise(binary,session,expected,limit,control=False):
    w=Worker(binary); pages=[]
    try:
        snapshot=w.call("open_snapshot",session=session)["snapshot"]
        n=len(expected); after=0; count=0
        if control:
            err=w.call("read_records",snapshot=snapshot,after_seq=n+1,limit=limit,error=True)
            assert "cursor" in str(err)
            first=w.call("read_records",snapshot=snapshot,after_seq=0,limit=limit)["page"]
            retry=w.call("read_records",snapshot=snapshot,after_seq=0,limit=limit)["page"]
            assert retry==first and first["records"]==expected[:len(first["records"])]
        # Full wire time includes JSON parsing needed to advance cursor. Deep output
        # equality checks below are outside each RPC timer; do not accumulate results.
        wall=cpu=0
        while True:
            u=w.cpu_ns(); t=time.perf_counter_ns()
            page=w.call("read_records",snapshot=snapshot,after_seq=after,limit=limit)["page"]
            wall+=time.perf_counter_ns()-t; cpu+=w.cpu_ns()-u
            records=page["records"]; k=len(records); pages.append(k)
            assert records==expected[count:count+k] and page["snapshot"]==snapshot
            count+=k
            if page["next_after_seq"] is None: break
            after=page["next_after_seq"]
            assert k and after==count
        assert count==n
        return {"wall_ms":wall/1e6,"worker_cpu_ms":cpu/1e6,"peak_kib":w.rss(),"pages":pages}
    finally: w.close()

def main(before,after):
    bins={"before":before,"after":after}; out={}
    with tempfile.TemporaryDirectory(dir=os.environ.get("PROTEUS_BENCH_TMPDIR", os.getcwd())) as tmp:
        root=Path(tmp)
        fixtures={name:seed(before,root/name,n,size) for name,n,size in
                  [("small",12,256),("large",8,2*1024*1024)]}
        for name,f,limit in [("short","small",64),("large_budget","large",64),("large_limit_one","large",1)]:
            session,expected=fixtures[f]; data={s:[] for s in bins}
            for i in range(13):
                for s in (["before","after"] if i%2==0 else ["after","before"]):
                    result=exercise(bins[s],session,expected,limit,control=not i)
                    if i: data[s].append(result)
            assert all(x["pages"]==data["before"][0]["pages"] for a in data.values() for x in a)
            out[name]=dict(limit=limit,records=len(expected),pages=data["before"][0]["pages"],
                median={s:{k:statistics.median(x[k] for x in a) for k in ["wall_ms","worker_cpu_ms","peak_kib"]} for s,a in data.items()},
                samples=data)
            print(name,out[name]["median"],file=sys.stderr,flush=True)
    print(json.dumps(out,indent=2))
if __name__=="__main__": main(*sys.argv[1:])
