"""Direct negotiated SDK parity + allocator counts; no elapsed metrics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from statistics import median
from fixture import sha
from rpc import Client

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('fixture',type=Path)
p.add_argument('reference',type=Path)
p.add_argument('meter',type=Path)
p.add_argument('output',type=Path)
p.add_argument('--composition',choices=['main','after-256'],required=True)
p.add_argument('--pairs',type=int,default=2)
a=p.parse_args()
r=a.fixture.resolve(strict=True)
m=json.loads((r/'fixture.json').read_text())
source=r/m['journal']
assert sha(source)==m['journal_sha256']
assert not a.output.exists() and a.pairs>=2
target=r/m['session_dir']
reference,meter=(p.resolve(strict=True) for p in (a.reference,a.meter))
if a.composition=='main':
    assert sha(reference)==m['worker_sha256']
os.environ['TMPDIR']=str(r/'temp')

def trial(mode):
    if mode=='fresh':
        os.environ['R60_STOCK_PATH']='1'
    else:
        os.environ.pop('R60_STOCK_PATH',None)
    b=reference if mode=='reference' else meter
    with Client(b,m['backend'],host_features=('display_projection',)) as cli:
        d=cli.call('open',path=str(target))['descriptor']
        result=cli.call('open_display_snapshot',session=d['session'])['projection']
        snapshot=result['snapshot']
        opaque=snapshot['snapshot_id'].encode()
        def digest():
            raw=cli.last_raw
            assert raw.count(opaque)==1 and len(opaque)==36
            return dict(sha256=hashlib.sha256(raw.replace(opaque,b'00000000-0000-0000-0000-000000000000')).hexdigest(),
                        frame_bytes=len(raw))
        assert snapshot['content_sha256']==m['canonical_digest']
        assert snapshot['revision']==m['canonical_snapshot_revision']
        assert len(result['state']['conversation']['messages'])==m['canonical_active']
        projection=dict(open_digest=digest(),pages=[])
        after=0
        seq=0
        while after is not None:
            page=cli.call('read_display_records',snapshot=snapshot,after_seq=after,limit=64)['page']
            assert page['snapshot']==snapshot
            for record in page['records']:
                seq+=1
                assert record['session_seq']==seq
            next_after=page['next_after_seq']
            projection['pages'].append(dict(after=after,next=next_after,records=len(page['records']),**digest()))
            after=next_after
        assert seq==m['exact_fresh_canonical_read_records']
        cli.call('release_snapshot',snapshot=snapshot)
    assert sha(source)==m['journal_sha256']
    assert len(cli.reports)==int(mode!='reference')
    return projection,(cli.reports[0] if cli.reports else None)
def measure():
    ref,_=trial('reference')
    results={arm:[] for arm in ('fresh','scratch')}
    for i in range(a.pairs):
        for a0 in (('fresh','scratch') if i%2==0 else ('scratch','fresh')):
            wire,counts=trial(a0)
            assert wire==ref
            results[a0].append(counts)
    paired=[[old-new for old,new in zip(a,b)] for a,b in zip(results['fresh'],results['scratch'])]
    meters={a:[median(c) for c in zip(*rows)] for a,rows in results.items()}
    saved=[old-new for old,new in zip(meters['fresh'],meters['scratch'])]
    if m['backend']=='jsonl':
        assert all(calls>0 and req>0 for calls,req in paired), paired
    else:
        assert all(diff==[0,0] for diff in paired), paired
    return results,meters,saved,ref,paired
results,med,saved,wire,paired=measure()
a.output.write_text(json.dumps({
    'composition':a.composition,'backend':m['backend'],'canonical_sha256':m['journal_sha256'],
    'binary_sha256':{'reference':sha(reference),'diagnostic':sha(meter)},
    'scope':'OpenDisplaySnapshot StorageService::execute, not SDK or Core allocation, count alloc/alloc_zeroed/realloc requested bytes',
    'comparisons':a.pairs,'orders':['fresh,scratch' if i%2==0 else 'scratch,fresh' for i in range(a.pairs)],
    'raw':results,'median':med,'saved':saved,'paired_saved':paired,'exact_normalized_wire_reference':wire,
    'normalized':'only opaque per-open 36-byte snapshot token',
},indent=2)+'\n')
