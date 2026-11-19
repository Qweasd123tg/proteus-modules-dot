"""Linux. Pass two actual release proteus-session-storage-module executables (before/after).
JSON-RPC over stdio. Session setup and post-ACK correctness checks are outside measured work; measured commits are real writes."""
import ctypes
import json
import os
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
    def __init__(self, binary, kind):
        self.kind=kind
        self.p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        if "PROTEUS_BENCH_WORKER_CPU" in os.environ:
            os.sched_setaffinity(self.p.pid,{int(os.environ["PROTEUS_BENCH_WORKER_CPU"])})
        self.seq=0
        clock=ctypes.c_int()
        assert ctypes.CDLL(None).clock_getcpuclockid(self.p.pid,ctypes.byref(clock))==0
        self.clock_id=clock.value
        self.frame("initialize", {"protocol_version":"v3","component_id":"storage-test",
            "exports":[{"slot":"session_storage","module_id":self.kind,"contract_version":"v1",
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
        return self.frame("execute",{"export":{"slot":"session_storage","module_id":self.kind},
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

def event(i,rev,lease,text):
    msg={"id":uid(2000+i),"role":"User","phase":None,"parts":[{"part_id":uid(4000+i),"provenance":"user","scope":"conversation","payload":{"Text":{"text":text}}}],"name":None,"tool_call_id":None,"metadata":{"api_key":"dummy-canary","case":"parity"}}
    return {"lease":lease,"operation_id":uid(100+i),"expected":rev,"timestamp_ms":1234+i,"attribution":{"execution_id":None,"thread_id":uid(222222),"turn_id":None},"entry":{"kind":"history_mutated","payload":{"previous_revision":i-1,"new_revision":i,"mutation":"append","messages":[msg],"compaction":None,"tool_results":[]}}}

def exercise(binary,kind,n,size,tmp,control):
    w=Worker(binary,kind)
    try:
        with tempfile.TemporaryDirectory(dir=tmp) as d:
            config=Path(d)/'config'; config.mkdir(); work=Path(d)/'work'; work.mkdir()
            desc=w.call('create',config_root=str(config),workspace_path=str(work),session_id=uid(42),parent_session_id=None)['descriptor']
            session=desc['session']; out=w.call('acquire_writer',session=session); lease=out['lease']; rev=out['revision']; cpu=wall=0; match_ack=[]
            pattern='some source: fn main() { println!("hey"); }\nПривет 世界 '; text=(pattern*((size+len(pattern)-1)//len(pattern)))[:size]; wire_bytes=len(text.encode()); wire_json=len(json.dumps(text,ensure_ascii=True).encode())
            for i in range(1,n+1):
                commit=event(i,rev,lease,text)
                c0=w.cpu_ns(); t=time.perf_counter_ns(); ack=w.call('commit',commit=commit)['ack']; wall+=time.perf_counter_ns()-t; cpu+=w.cpu_ns()-c0
                rev=ack['revision']; expected=event(i,commit['expected'],lease,text); expected['entry']['payload']['messages'][0]['metadata']['api_key']='[REDACTED]'
                assert ack['record']['entry']==expected['entry'], (ack['record']['entry']['payload']['messages'][0]['metadata'],expected['entry']['payload']['messages'][0]['metadata'])
                assert ack['record']['session_id']==uid(42) and ack['record']['session_seq']==i and ack['record']['timestamp_ms']==1234+i and ack['record']['thread_id']==uid(222222) and ack['operation_id']==uid(100+i) and rev=={'session_seq':i,'history_revision':i}; match_ack.append(ack['record'])
            hwm=w.rss()
            if control:
                assert w.call('commit',commit=commit)['ack']==ack
                changed=event(n,commit['expected'],lease,'changed'); assert 'conflict' in str(w.call('commit',commit=changed,error=True)).lower(); bad={**commit,'expected':{**commit['expected'],'session_seq':3}}; assert 'changed its original' in str(w.call('commit',commit=bad,error=True))
                w.call('release_writer',lease=lease); w.close(); w=Worker(binary,kind); snap=w.call('open_snapshot',session=session)['snapshot']; page=w.call('read_records',snapshot=snap,after_seq=0,limit=64)['page']; assert page['records']==match_ack and page['next_after_seq'] is None
            return {'wall_us_per_commit':wall/1e3/n,'worker_cpu_us_per_commit':cpu/1e3/n,'worker_peak_kib':hwm,'text_utf8_bytes':wire_bytes,'json_string_wire_bytes':wire_json}
    finally: w.close()

def main():
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('before');p.add_argument('after');p.add_argument('--pairs',type=int,default=8);p.add_argument('--large-chars',type=int,default=2*1024*1024);p.add_argument('--tmpdir',default=None);p.add_argument('--out',required=True); a=p.parse_args(); out=[]
    for kind in ['jsonl','sqlite']:
        for n,size in [(20,160),(1,a.large_chars)]:
            for r in range(a.pairs+1):
                for side,binary in ([('before',a.before),('after',a.after)] if r%2==0 else [('after',a.after),('before',a.before)]):
                    val=exercise(binary,kind,n,size,a.tmpdir,not r);out.append(dict(backend=kind,n=n,size=size,pair=r,side=side,**val)); Path(a.out).write_text(json.dumps(out,indent=2));
            rows=[x for x in out if x['backend']==kind and x['n']==n and x['pair']]; print(kind,n,{s:{k:round(statistics.median(x[k] for x in rows if x['side']==s),2) for k in ['wall_us_per_commit','worker_cpu_us_per_commit','worker_peak_kib']} for s in ['before','after']},flush=True)
if __name__=='__main__': main()
