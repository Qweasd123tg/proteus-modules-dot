"""Classify accepted/different HTML in the published controlled Desktop transport trace.

One retained content surface, no inline slots, fixed language and renderer. Counts
candidates only; no native TextView, worker, viewport, or paint is presumed.
"""
import argparse
import hashlib
import json
from pathlib import Path

HASH = '300becb4c7948843b3f6ae65347fb7dc66891b055b2a394bf47bb778913f4884'
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('proofs',type=Path)
args=p.parse_args()
blob=args.proofs.read_bytes()
assert hashlib.sha256(blob).hexdigest()==HASH
stats={}
for key,case in json.loads(blob)['cases'].items():
    proofs=case['proofs']
    n,group,mode=case['count'],case['group'],case['mode']
    assert len(proofs)==len(case['sent_revisions'])
    assert [x['rev'] for x in proofs]==case['sent_revisions']
    # The real host drains after each group; only the then-current revision
    # is accepted. For forced invalidations the source revision remains zero.
    if mode=='grow':
        newest=set(range(group-1,n,group))|{n-1}
        accepted=[x for x in proofs if x['rev'] in newest]
    else:
        accepted=proofs
    assert len(accepted)==case['accepted']
    prev=None
    changed=[]
    for x in accepted:
        if prev!=x['html_sha256']:
            changed.append(x)
            prev=x['html_sha256']
    elig=[x['html_bytes'] for x in changed if x['html_bytes']<=4096]
    stats[key]={'responses':len(proofs),'accepted':len(accepted),
                'new_or_changed_html':len(changed),'eligible_under_or_equal_4096':len(elig),
                'eligible_html_bytes':elig}
print(json.dumps({'source_sha256':HASH,'cases':stats},indent=2))
