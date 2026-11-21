"""Read an existing private sealed derived set via actual SDK; no mutation or elapsed."""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path

from rpc import Client

p=argparse.ArgumentParser()
p.add_argument('fixture',type=Path)
p.add_argument('stock',type=Path)
p.add_argument('meter',type=Path)
p.add_argument('out',type=Path)
p.add_argument('--reference',type=Path,help='equivalent composed worker reference (optional)')
a=p.parse_args()
assert not a.out.exists()
r=a.fixture.resolve(strict=True)
m=json.loads((r/'fixture.json').read_text())
manifest=json.loads((r/'baseline-view.json').read_text())
target=r/m['session_dir']
journal=r/m['journal']
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def token(b): return hashlib.sha256(b).hexdigest()
def filename(k): return '.storage-cache-'+token(k.encode())+'.json'
def current():
    return {p.name:sha(p) for p in target.glob('.storage-cache-*.json')}
assert current()==manifest['documents']
assert sha(journal)==m['journal_sha256']==manifest['journal_sha256']
assert m['rows']==125000 and m['backend']=='jsonl'
assert sha(a.stock)==m['worker_sha256']
expected=manifest['documents']
assert len(expected)==320
def referenced(value):
    if isinstance(value,list):
        for v in value: yield from referenced(v)
    elif isinstance(value,dict):
        for v in value.values(): yield from referenced(v)
    elif isinstance(value,str) and len(value)==64 and all(c in 'abcdef0123456789' for c in value):
        yield value
head='display-view-v1-head'
head_snapshot=json.loads((target/filename(head)).read_text())['source']
session=head_snapshot['session']
assert head_snapshot['content_sha256']==m['journal_sha256']
pending=deque([head,'display-view-v1-prefix','display-revision-'+manifest['target_revision']])
keys={}
while pending:
    k=pending.popleft()
    if k in keys: continue
    path=target/filename(k)
    assert path.name in expected,(k,path.name)
    cache=json.loads(path.read_text())
    assert cache['source']['session']==session
    keys[k]=(path,cache['value'])
    for digest in referenced(cache['value']):
        label='display-data-'+digest
        if label not in keys and filename(label) in expected: pending.append(label)
assert {p.name for p,_ in keys.values()}==set(expected)
ordered=sorted(keys)
assert len(ordered)==len(expected)
miss='r62-synthetic-control-not-yet-published'
assert filename(miss) not in expected

def io(p):
    values=dict(l.split(':',1) for l in Path(f'/proc/{p}/io').read_text().splitlines())
    return int(values['syscr']),int(values['rchar'])
def trial(arm):
    ref=a.reference or a.stock
    binary=(ref if arm=='reference' else a.meter).resolve(strict=True)
    if arm=='default':
        os.environ['R62_FORCE_DEFAULT']='1'
    else:
        os.environ.pop('R62_FORCE_DEFAULT',None)
    with Client(binary,'jsonl') as cli:
        before=io(cli.p.pid)
        frames=[]; etags=[]
        for key in ordered:
            document=cli.call('read_cache',session=session,key=key,source=None)['document']
            assert document is not None and document['value']==keys[key][1]
            assert len(document['etag'])==64
            etags.append(document['etag'])
            frames.append(token(cli.last_raw))
        after=io(cli.p.pid)
        no=cli.call('read_cache',session=session,key=miss,source=None)['document']
        assert no is None
        absent=token(cli.last_raw)
        expected=cli.call('read_cache',session=session,key=head,source=head_snapshot)['document']
        assert expected and expected['value']==keys[head][1]
        current_source=token(cli.last_raw)
    assert sha(journal)==m['journal_sha256']
    assert len(cli.reports)==(0 if arm=='reference' else 2)
    op=[dict(requests=n,allocation_calls=c,allocation_requested_bytes=b) for n,c,b in cli.reports]
    wire=dict(hit_response_sha256=frames,hit_etags=etags,missing_response_sha256=absent,
              matching_source_head_response_sha256=current_source)
    counts=dict(actual_sdk_worker_syscr=after[0]-before[0],actual_sdk_worker_rchar=after[1]-before[1],
                hit_scope=op[0] if op else None,missing_scope=op[1] if op else None)
    return wire,counts
ref,_=trial('reference')
results={'default':[],'hint':[]}
for pair in [('default','hint'),('hint','default')]:
    for arm in pair:
        wire,counts=trial(arm)
        assert wire==ref
        results[arm].append(counts)
for old,new in zip(results['default'],results['hint']):
    assert old['hit_scope']['requests']==new['hit_scope']['requests']==320
    assert old['hit_scope']['allocation_calls']>new['hit_scope']['allocation_calls']
    assert old['hit_scope']['allocation_requested_bytes']>new['hit_scope']['allocation_requested_bytes']
    assert old['actual_sdk_worker_syscr']>new['actual_sdk_worker_syscr']
    assert old['missing_scope']==new['missing_scope']
assert current()==expected and sha(journal)==m['journal_sha256']
lengths=[p.stat().st_size for p,_ in keys.values()]
a.out.write_text(json.dumps(dict(
    exact_normalization='none, complete original raw SDK response frames',
    stock_sha256=sha(a.stock), reference_sha256=sha(a.reference or a.stock),
    meter_sha256=sha(a.meter), source_sha256=m['journal_sha256'],
    files=len(lengths),files_at_most_64k=sum(v<=65536 for v in lengths),bytes=sum(lengths),
    order=['default,hint','hint,default'],raw=results,wire_reference=ref,
    scopes={'alloc':'worker StorageService::execute ReadCache, including path/JSON/ETag, excluding SDK serialization',
        'syscr':'actual SDK worker Linux read-family delta while serving 320 hits, includes request/identity reads, not isolated file calls'}
),indent=2)+'\n')
