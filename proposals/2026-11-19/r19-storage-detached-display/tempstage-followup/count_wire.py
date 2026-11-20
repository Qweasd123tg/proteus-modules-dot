"""Byte-transparently forward the synthetic worker protocol and count request op tags."""
import json, os, subprocess, sys, threading
from pathlib import Path

def copy():
    while chunk:=os.read(p.stdout.fileno(),65536):
        view=memoryview(chunk)
        while view:
            view=view[os.write(1,view):]

binary, log=sys.argv[1:3]
p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=0)
out=threading.Thread(target=copy,daemon=True)
out.start()
with Path(log).open('w',buffering=1) as f:
    try:
        for line in sys.stdin.buffer:
            r=json.loads(line)
            if r.get('method')=='execute':
                op=(r.get('params') or {}).get('params') or {}
                if isinstance(op, dict):
                    f.write(' '.join([str(op.get('operation','missing-op')), str((op.get('snapshot') or {}).get('snapshot_id','-')),str(op.get('after_seq','-'))])+'\n')
            view=memoryview(line)
            while view:
                view=view[os.write(p.stdin.fileno(),view):]
    finally:
        p.stdin.close()
p.wait()
out.join()
sys.exit(p.returncode)
