#!/usr/bin/env python3
"""Exercise unmodified Metrics, Recorder and Tree with a deterministic fake /proc."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path('/workspace/shared/benchmark-design-audit')
sys.path.insert(0, str(ROOT / 'examples/performance/history-scale'))
from measurement import Metrics, Tree


def process(proc, cpu):
    path = proc / '100'
    path.mkdir(exist_ok=True)
    fields = ['0'] * 22
    fields[0], fields[1], fields[11], fields[19] = 'S', '1', str(cpu), '100'
    (path / 'stat').write_text('100 (synthetic-backend) ' + ' '.join(fields))
    (path / 'smaps_rollup').write_text('Rss: 100 kB\nPss: 80 kB\nSwapPss: 0 kB\nPrivate_Clean: 1 kB\nPrivate_Dirty: 1 kB\n')
    (path / 'io').write_text('rchar: 0\nwchar: 0\nread_bytes: 0\nwrite_bytes: 0\n')
    (path / 'status').write_text('VmHWM: 100 kB\nThreads: 1\n')
    (path / 'cmdline').write_bytes(b'/synthetic-backend\0')


def scenario(boundary_sample=False):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        proc = root / 'proc'
        proc.mkdir()
        (proc / 'uptime').write_text('1000.0 0\n')
        process(proc, 0)
        tree = Tree(100, root_group='backend', proc=proc)
        tree.clock_ticks = 100
        metrics = Metrics(tree, root, SimpleNamespace(max_pss_mib=100, timeout=600))
        now = [1_000_000_000]
        with patch('time.monotonic_ns', side_effect=lambda: now[0]):
            metrics.mark('first_launch')
            metrics.sample()
            # Exactly 1 CPU-second accrued BEFORE declaring idle.
            now[0] = 2_000_000_000
            process(proc, 100)
            if boundary_sample:
                metrics.sample()
            metrics.mark('first_resident_idle')
            metrics.sample()
            # No CPU is consumed anywhere in this idle period.
            now[0] = 3_000_000_000
            metrics.sample()
            report = metrics.summary()
            metrics.close()
        events = [json.loads(line) for line in (root / 'samples.jsonl').read_text().splitlines()]
        return {'expected_idle_cpu_percent': 0,
                'actual_idle_cpu_percent': report['phases']['first_resident_idle']['cpu_percent_one_core_weighted_mean'],
                'launch_cpu_ticks': report['phases']['first_launch']['observed_interval_counters']['cpu_ticks'],
                'idle_cpu_ticks': report['phases']['first_resident_idle']['observed_interval_counters']['cpu_ticks'],
                'events': events, 'summary': report}


if __name__ == '__main__':
    result = {'unmodified_transition': scenario(False), 'boundary_sample_positive_control': scenario(True)}
    destination = Path(__file__).with_name('phase-cpu-result.json')
    destination.write_text(json.dumps(result, indent=2) + '\n')
    for name, result in result.items():
        print(name, json.dumps({k:v for k,v in result.items() if k not in ('events','summary')}))
