"""Machine-readable client-only slice from up to N full stand summaries, no IO on HTTP."""
import argparse, json
from pathlib import Path

def phase(items):
    succeeded=[r for r in items if r['ok']]
    errors=[{k:r[k] for k in ('id','session_leaf','mode','error','api_ms') if k in r} for r in items if not r['ok']]
    return dict(n=len(items),ok=len(succeeded),ok_within_30s=sum(r['api_ms']<30_000 for r in succeeded),
                max_call_ms=max((r['api_ms'] for r in items),default=None),
                min_call_ms=min((r['api_ms'] for r in items),default=None),
                max_success_ms=max((r['api_ms'] for r in succeeded),default=None),errors=errors)
def run(path):
    if path.is_dir(): path=path/'summary.json'
    s=json.loads(path.read_text())
    assert s['client']=='pinned real Desktop Api', str(path)+': not Desktop'
    reqs=sorted(s['desktop_api_requests'],key=lambda v:int(v['id']))
    assert [int(x['id']) for x in reqs]==list(range(len(reqs))), 'missing or duplicate observations'
    cold=s['cold'];warm=s['warm']
    # Stand sends one active verification, then waits for each group before the
    # next so concurrent responses can finish out of order only within a group.
    counts=[len(cold),len(warm['pinned']),len(warm['latest'])]
    assert len(reqs)==sum(counts)+2
    offset=1; groups={}
    for key,count,outer in zip(('first_tail','warm_pinned','warm_tail'),counts,(cold,warm['pinned'],warm['latest'])):
        group=reqs[offset:offset+count];offset+=count
        if any('mode'in r for r in group):assert all(r['mode']==('pinned' if key=='warm_pinned' else 'latest') for r in group)
        groups[key]=phase(group)
        groups[key]['typed_page_and_golden_ok']=sum(x['ok'] for x in outer)
    return dict(arm=path.parent.name,state=s.get('index_state'),stand_passed=s['passed'],
                core_sha256=s['core_sha256'],worker_sha256=s['worker_sha256'],groups=groups,
                durable_foreground=s['hot_canonical']['durable_success'],
                canonical_sha_unchanged=s['canonical_sha_before']==s['canonical_sha_after'])
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('summary',nargs='+',type=Path)
    print(json.dumps([run(f) for f in p.parse_args().summary],indent=2))
