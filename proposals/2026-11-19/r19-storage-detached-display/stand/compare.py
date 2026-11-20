#!/usr/bin/env python3
"""Compare exactly one changed binary, distinguish an unsuccessful arm from a latency sample."""
import argparse,json
from pathlib import Path
def main():
    p=argparse.ArgumentParser()
    p.add_argument('a',type=Path);p.add_argument('b',type=Path)
    p.add_argument('--axis',choices=['core','worker'],required=True)
    a=p.parse_args(); A,B=(json.loads(k.read_text()) for k in (a.a,a.b))
    for field in ('archives','rows','reference_sha256','stand_sha256','profile_sha256','sampler_sha256','fixture_manifest_sha256','canonical_sha_before','client_socket_timeout_s'):
        if A.get(field) is None or A[field]!=B.get(field): raise SystemExit('non-equivalent inputs: '+field)
    changed=[k for k in ('core','worker') if A[k+'_sha256']!=B[k+'_sha256']]
    if changed!=[a.axis]: raise SystemExit('expected only '+a.axis+' to differ; observed: '+str(changed))
    def arm(s):
        hot=s.get('hot',{});cold=s.get('cold',[])
        times=lambda rs: [r['ms'] if r['ok'] else None for r in rs]
        return dict(passed=s['passed'],canonical_unchanged=s['canonical_sha_before']==s.get('canonical_sha_after'),cold_completed=sum(r['ok'] for r in cold),cold_ms=times(cold),cold_failures=[(r['index'],r['error'],r['ms']) for r in cold if not r['ok']],durable_hot=s.get('hot_canonical',{}).get('durable_success'),hot_durable_open_upper_bound_ms=hot.get('durable_open_upper_bound_ms'),hot_first_text_ms=hot.get('first_text_ms'),hot_terminal_ms=(hot.get('ms') if hot.get('received_success') else None),hot_error=(None if hot.get('received_success') else {k:hot.get(k) for k in ('reply','error','ms')}),cold_peak_tree_pss_kib=s.get('phases',{}).get('cold',{}).get('peak_pss_kib'),warm={k:times(v) for k,v in s.get('warm',{}).items()})
    print(json.dumps(dict(scope='one paired observation, no distribution or causality claim',changed=changed,A=arm(A),B=arm(B)),indent=2))
if __name__=='__main__':main()
