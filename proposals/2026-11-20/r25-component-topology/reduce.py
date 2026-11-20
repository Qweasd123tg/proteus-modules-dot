"""Validate topology, journal parity, and report bounded process-tree PSS."""
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

root = Path(sys.argv[1])
modes = ('split-1', 'aggregate-1', 'aggregate-2', 'split-2')
inputs = [json.loads((root/m/'binaries.json').read_text()) for m in modes]
assert all(b == inputs[0] for b in inputs)
runs = []
answer = None
for mode in modes:
    fanout = 4 if mode.startswith('split') else 1
    for n in (1, 5, 10):
        directory = root/mode/f'peers-{n}-repeat-0'
        r = json.loads((directory/'report.json').read_text())
        assert r['status'] == 'passed' and r['rounds'] == 1 and r['idle_cap'] == n
        assert r['model_overlap'] == dict(maximum_in_flight=n, model_calls=2*n)
        checkpoints = {e['phase']: e['elapsed_ms'] for e in r['events']}
        def complete(s):
            rows = s['processes']
            cores = [p for p in rows if p['name'] == 'core-stock']
            refs = [p for p in rows if p['name'] == 'proteus-referen']
            workers = [p for p in rows if p['name'] == 'worker-stock']
            drivers = [p for p in rows if p['name'] == 'driver']
            if (len(cores), len(refs), len(workers), len(drivers), len(rows)) != (n, fanout*(n+1), n+1, 1, (fanout+2)*(n+1)):
                return False
            parent = drivers[0]['pid']
            if any(p['parent'] != parent for p in cores):
                return False
            return all(sum(q['parent'] == pid for q in refs) == fanout and
                       sum(q['parent'] == pid for q in workers) == 1
                       for pid in [parent, *(p['pid'] for p in cores)])
        resident_all = [s for s in r['samples'] if s['phase']=='resident_idle']
        idle = [s for s in resident_all if complete(s)]
        active = [s for s in r['samples'] if s['phase']=='all_models_entered' and complete(s)]
        assert len(idle) >= 5 and len(active) >= 5, (mode,n)
        peak_sample = max(r['samples'], key=lambda s:s['pss_swap_kib'])
        journals = list((directory/'config/sessions').rglob('journal.jsonl'))
        assert len(journals) == n and all(j['replay_matched'] for j in r['journals'])
        payload = (directory/'workspace/payload.txt').read_bytes()
        want = b'Fake final answer after tool result:\n'+payload
        for journal in journals:
            records = [json.loads(l) for l in journal.read_text().splitlines()]
            assert records[-1]['kind'] == 'turn_settled'
            assert records[-1]['payload']['value']['output']['text'].encode() == want
            assert sum(v['kind']=='model_request_recorded' for v in records)==2
            assert sum(v['kind']=='tool_effect_recorded' for v in records)==1
            digest = hashlib.sha256(want).hexdigest()
            if answer is None:
                answer = digest
            assert digest == answer
        def mib(kib):
            return round(kib/1024, 3)
        runs.append(dict(mode=mode, peers=n, processes=len(idle[0]['processes']),
                         peak_mib=mib(peak_sample['pss_swap_kib']),
                         peak_swap_kib=sum(row['SwapPss'] for row in peak_sample['processes']),
                         active_mib=mib(median(s['pss_swap_kib'] for s in active)),
                         active_samples=len(active), idle_mib=mib(median(s['pss_swap_kib'] for s in idle)),
                         idle_samples=len(idle), idle_transition_excluded=len(resident_all)-len(idle),
                         round_ms=round(checkpoints['round_settled']-checkpoints['round_start'], 3),
                         last_tool_entered_ms=round(checkpoints['all_models_entered']-checkpoints['round_start'], 3),
                         replayed_journals=len(journals), model_calls=2*n))
report=dict(binaries={k:v['sha256'] for k,v in inputs[0].items()}, answer_sha256=answer, runs=runs)
print(json.dumps(report, indent=2))
