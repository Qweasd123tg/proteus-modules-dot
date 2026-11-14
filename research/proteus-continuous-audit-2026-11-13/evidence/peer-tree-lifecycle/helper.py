"""Bounded fixture-owned marker process. No external state or network."""
import json,os,signal,sys,time
from pathlib import Path
signal.alarm(15)
cwd=Path(sys.argv[1]);workflow=int(sys.argv[2]);core=int(sys.argv[3]);mode=sys.argv[4]
with (cwd/'markers.jsonl').open('a') as f:
    f.write(json.dumps({'name':'helper-started','pid':workflow,'ppid':core,'helper_pid':os.getpid(),'helper_ppid':os.getppid(),'pgid':os.getpgrp(),'time':time.time(),'mode':mode})+'\n')
time.sleep(4)
(cwd/'after-timeout-marker.json').write_text(json.dumps({'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'time':time.time()}))
time.sleep(20)
