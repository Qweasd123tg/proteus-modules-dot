"""Measure native WriteCache (not entire turn) against a controlled populated cache.
Linux only; elapsed worker CPU via clock_getcpuclockid; CPU affinity optional.
Seeds are real independent cache envelopes, generated once by this worker, cloned 
onto distinct computed key filenames outside the timing window. N is a synthetic 
file count, not a transcript message count. No O(N^2) setup through WriteCache.
"""
import argparse, ctypes, hashlib, json, os, statistics, subprocess, sys, tempfile, time, uuid
from pathlib import Path

class Worker:
    def __init__(self, path, kind, cpu):
        self.p = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        if cpu is not None: os.sched_setaffinity(self.p.pid, {cpu})
        self.kind = kind
        ident = ctypes.c_int()
        assert ctypes.CDLL(None).clock_getcpuclockid(self.p.pid, ctypes.byref(ident)) == 0
        self.clock_id = ident.value
        self.seq = -1
        self.frame('initialize', {'protocol_version':'v3', 'component_id':'storage-test',
                   'exports':[{'slot':'session_storage', 'module_id':kind, 'contract_version':'v1',
                               'composition':'select_one', 'module_config':{}, 'host_features':[]}]})
    def frame(self, method, params):
        self.seq += 1
        token = f'h:1:{self.seq}'
        self.p.stdin.write(json.dumps({'jsonrpc':'2.0','id':token,'method':method,'params':params},
                                      separators=(',',':')).encode()+b'\n')
        self.p.stdin.flush()
        reply = json.loads(self.p.stdout.readline())
        assert reply['id']==token and 'error' not in reply, reply
        return reply['result']
    def call(self, op, **args):
        return self.frame('execute', {'export':{'slot':'session_storage','module_id':self.kind},
                          'lineage':{'root_invocation_id':f'h:1:{self.seq+1}','parent_invocation_id':None,'depth':0},
                          'params':{'operation':op,**args}})
    def cpu_ns(self):
        return time.clock_gettime_ns(self.clock_id)
    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=10)
        self.p.stdout.close()

def cache_file(key):
    return '.storage-cache-'+hashlib.sha256(key.encode()).hexdigest()+'.json'

def run(args, kind, n, run_no):
    w=Worker(args.worker,kind,args.cpu)
    try:
        with tempfile.TemporaryDirectory(dir=args.tmpdir) as tmp:
            cfg=Path(tmp)/'cfg'; work=Path(tmp)/'work'; cfg.mkdir(); work.mkdir()
            desc=w.call('create',config_root=str(cfg),workspace_path=str(work),
                        session_id=str(uuid.UUID(int=42)),parent_session_id=None)['descriptor']
            session=desc['session']; dir=Path(desc['local_path'])
            lease=w.call('acquire_writer',session=session)['lease']
            snapshot=w.call('open_snapshot',session=session)['snapshot']
            def put(key, value):
                response=w.call('write_cache',session=session,source=snapshot,key=key,value=value)
                assert response.get('etag') is not None, response
                return response['etag']
            assert put('warm-bench-key', {'version':0})
            fixed=dir/cache_file('warm-bench-key')
            seed=fixed.read_bytes()
            for i in range(n):
                f=dir/cache_file('seed-'+str(i)); f.write_bytes(seed)
                if args.shuffled_times:
                    stamp=1_650_000_000_000_000_000 + ((i*2654435761) % (2**32))
                    os.utime(f,ns=(stamp,stamp))
            initial=sorted(p.name for p in dir.glob('.storage-cache-*.json'))
            assert len(initial)==n+1 and sum(p.stat().st_size for p in dir.glob('.storage-cache-*.json'))<128*1024*1024
            # Overwrite the same fixed-size header; effective population stays N+1.
            data=[]
            for i in range(args.writes+2):
                t0=w.cpu_ns(); wall=time.perf_counter_ns()
                etag=put('warm-bench-key',{'version':i%9})
                elapsed=time.perf_counter_ns()-wall; cpu=w.cpu_ns()-t0
                if i>=2: data.append({'worker_cpu_us':cpu/1000,'wall_us':elapsed/1000})
            check=w.call('read_cache',session=session,source=snapshot,key='warm-bench-key')['document']
            assert check=={'etag':etag,'value':{'version':(args.writes+1)%9}},check
            assert sorted(p.name for p in dir.glob('.storage-cache-*.json'))==initial
            w.call('release_writer',lease=lease)
            return dict(backend=kind,seed_files=n,run=run_no,file_bytes=len(seed),samples=data)
    finally: w.close()

def main():
    p=argparse.ArgumentParser(); p.add_argument('worker');p.add_argument('--tmpdir',default='/tmp')
    p.add_argument('--counts',default='0,256,2048,8192');p.add_argument('--backends',default='jsonl,sqlite')
    p.add_argument('--runs',type=int,default=3);p.add_argument('--writes',type=int,default=9)
    p.add_argument('--shuffled-times',action='store_true');p.add_argument('--cpu',type=int);p.add_argument('--out',required=True)
    a=p.parse_args(); rows=[]
    for r in range(a.runs):
        counts=[int(n) for n in a.counts.split(',')]; 
        if r%2: counts.reverse()
        for kind in a.backends.split(','):
            for n in counts:
                row=run(a,kind,n,r);rows.append(row);Path(a.out).write_text(json.dumps(rows,indent=2)+'\n')
                print(kind,n,r,{k:round(statistics.median(x[k] for x in row['samples']),1) for k in row['samples'][0]},flush=True)
if __name__=='__main__': main()
