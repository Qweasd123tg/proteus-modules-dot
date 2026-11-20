"""Concurrent JSONL bridge into one pinned Desktop Api (connection pool shared).
Python never dials the HTTP history endpoint or changes its deadlines.
"""
import concurrent.futures, itertools, json, subprocess, threading
from pathlib import Path
class DesktopApi:
    def __init__(self, origin, exe=None):
        here=Path(__file__).resolve().parent
        self.proc=subprocess.Popen([exe or here/'client',origin,'--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
        ready=self.proc.stdout.readline()
        if not ready or json.loads(ready)!={'ready':True}:raise RuntimeError('Rust harness did not start')
        self.lock=threading.Lock();self.counter=itertools.count();self.pending={};self.observed=[]
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
    def _read(self):
        failure=EOFError('Rust harness stopped')
        try:
            for line in self.proc.stdout:
                r=json.loads(line)
                with self.lock:
                    f,meta=self.pending.pop(r['id'])
                    self.observed.append({**meta,**{k:r[k] for k in ('id','ok','api_ms','error') if k in r}})
                f.set_result(r)
        except Exception as e: failure=e
        finally:
            with self.lock:
                failed=list(self.pending.values());self.pending.clear()
            for f,_ in failed:f.set_exception(failure)
    def page(self,d,**kw):
        if set(kw) not in (set(), {'before','revision'}):raise ValueError(f'wrong options: {kw.keys()}')
        f=concurrent.futures.Future()
        with self.lock:
            ident=str(next(self.counter))
            self.pending[ident]=(f,dict(session_leaf=Path(d).name,mode='pinned' if kw else 'latest',**kw))
            self.proc.stdin.write(json.dumps(dict(id=ident,dir=str(d),**kw))+'\n')
            self.proc.stdin.flush()
        # Driver has its own 30 s HTTP timeout. Extra guard only catches a dead harness.
        r=f.result(timeout=60)
        if not r['ok']:raise RuntimeError(f"Desktop Api after {r['api_ms']:.2f} ms: {r['error']}")
        return r['page']
    def close(self):
        self.proc.stdin.close()
        try:self.proc.wait(65)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait();raise
        self.reader.join(3);self.proc.stdout.close()
        if self.proc.returncode!=0: raise RuntimeError('Rust harness exited '+str(self.proc.returncode))
    def __enter__(self):return self
    def __exit__(self,*a):self.close()
