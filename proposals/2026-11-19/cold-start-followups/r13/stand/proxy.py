#!/usr/bin/env python3
"""Transparent byte-preserving newline-JSON tap for synthetic storage fixtures only.
Log only monotonic times, lengths and routing keys; do not log payload content.
All frames are forwarded unmodified; no injected service calls.
"""
import csv,os,sys,time,threading,subprocess,re
from pathlib import Path
def field(name): return re.compile(b'"'+name+b'"\\s*:\\s*"([^"]+)"')
ident,method,op=map(field,[b'id',b'method',b'operation'])
def val(p,b,default=''):
    m=p.search(b)
    return m[1].decode('ascii','replace') if m else default
def now(): return time.monotonic_ns()
here=Path(__file__).resolve().parent
worker=(here/'worker').resolve(strict=True)
p=subprocess.Popen([str(worker),*sys.argv[1:]],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
with (here/f'wire-{os.getpid()}.csv').open('w',buffering=1) as f:
    writer=csv.writer(f)
    writer.writerow('id op kind cache_key_class request_bytes response_bytes req_done_ns worker_response_done_ns'.split())
    pending={}; lock=threading.Lock()
    def forward():
        try:
            for b in sys.stdin.buffer:
                reqt=now()
                # Outer JSON-RPC id is serialized before any nested payload.
                i=val(ident,b); operation=val(op,b,val(method,b)); kind=''
                if operation=='commit':
                    # Only the top-level entry kind in this synthetic fixture.
                    pos=b.find(b'"entry"')
                    if pos>=0: kind=val(field(b'kind'),b[pos:pos+256])
                cache_class=''
                if operation in ('read_cache','write_cache'):
                    m=re.search(br'"key"\s*:\s*"(display-view-v1-(?:prefix|head)[^"]*|display-data-[0-9a-f]{64})"',b)
                    if m:
                        k=m[1].decode()
                        if k.startswith('display-data-'): cache_class='display-data-<hash>'
                        elif k.startswith('display-view-v1-head-'): cache_class='display-view-v1-head-<revision>'
                        else: cache_class=k
                with lock: pending[i]=(operation,kind,cache_class,len(b),reqt)
                p.stdin.write(b); p.stdin.flush()
        except BrokenPipeError: pass
        finally:
            try: p.stdin.close()
            except BrokenPipeError: pass
    t=threading.Thread(target=forward,daemon=True);t.start()
    try:
        for b in p.stdout:
            resp=now(); i=val(ident,b)
            with lock: a=pending.pop(i,None)
            if a:
                operation,kind,cache_class,sz,req=a
                writer.writerow([i,operation,kind,cache_class,sz,len(b),req,resp])
            else: writer.writerow([i,'!unmatched','','',0,len(b),0,resp])
            sys.stdout.buffer.write(b); sys.stdout.buffer.flush()
    except BrokenPipeError: pass
    sys.exit(p.wait())
