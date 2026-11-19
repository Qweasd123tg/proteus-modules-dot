"""Paired isolated process-level logical live Rust heap, separate from time/traffic."""
import argparse
import hashlib
import json
import os
import statistics
import subprocess
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('binaries',type=Path)
p.add_argument('corpus',type=Path)
p.add_argument('--cpu',type=int,default=max(os.sched_getaffinity(0)))
a = p.parse_args()
bins = [a.binaries/(name+'-live') for name in ('stock','after')]
out = {'cpu': a.cpu, 'elf_sha256':[hashlib.sha256(x.read_bytes()).hexdigest() for x in bins],'cases':{}}
assert len(set(out['elf_sha256'])) == 2
for name in ('typical32','edge32','control32'):
    runs=[[],[]]
    for pair in range(4):
        for side in ([0,1] if pair%2 == 0 else [1,0]):
            row=json.loads(subprocess.check_output(
                [bins[side],a.corpus,name],preexec_fn=lambda:os.sched_setaffinity(0,{a.cpu}),
                timeout=30,
            ))
            assert row['fg']==(0 if name=='control32' else 32)
            assert row['bg']==(32 if side==0 or name=='control32' else 0)
            runs[side].append(row)
    med={field:[statistics.median(x[field] for x in group) for group in runs]
         for field in ('sync_delta','held_idle_delta','peak_delta','after_drop_delta')}
    out['cases'][name]={'runs':runs,'median_bytes_above_warm_process_baseline':med}
print(json.dumps(out,indent=2))
