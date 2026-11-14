#!/usr/bin/env python3
"""Owned synthetic child only: consume CPU before readiness, then block in stdin."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path('/workspace/shared/benchmark-design-audit')
sys.path.insert(0, str(ROOT / 'examples/performance/history-scale'))
from measurement import Metrics, Tree

CHILD = '''import sys,time
print("ready",flush=True)
for line in sys.stdin:
 if line.strip() == "burn":
  stop = time.process_time() + .25
  while time.process_time() < stop: pass
  print("done",flush=True)
'''

def run(boundary):
    with tempfile.TemporaryDirectory() as directory:
        p = subprocess.Popen([sys.executable,'-u','-c',CHILD], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            assert p.stdout.readline().strip() == 'ready'
            metrics = Metrics(Tree(p.pid,root_group='backend'),Path(directory),SimpleNamespace(max_pss_mib=100,timeout=20))
            metrics.mark('launch')
            metrics.sample()
            p.stdin.write('burn\n'); p.stdin.flush()
            assert p.stdout.readline().strip() == 'done'
            if boundary:
                metrics.sample()
            metrics.mark('resident_idle')
            metrics.sample()
            time.sleep(.25)
            metrics.sample()
            result = metrics.summary()['phases']
            metrics.close()
            return {name:{'cpu_percent': row['cpu_percent_one_core_weighted_mean'], 'cpu_ticks': row['observed_interval_counters']['cpu_ticks']} for name,row in result.items()}
        finally:
            p.stdin.close()
            p.wait(timeout=5)
            p.stdout.close()

result = {'unmodified_transition':run(False),'boundary_sample_positive_control':run(True)}
Path(__file__).with_name('live-phase-cpu-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
