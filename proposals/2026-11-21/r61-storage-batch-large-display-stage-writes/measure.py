"""Count actual Linux worker writes around staging; no timestamps."""
import argparse, hashlib, json, os
from pathlib import Path
from fixture import sha
from rpc import Client

p=argparse.ArgumentParser()
p.add_argument('stock',type=Path)
p.add_argument('meter',type=Path)
p.add_argument('out',type=Path)
p.add_argument('fixtures',type=Path,nargs=3)
a=p.parse_args()
assert not a.out.exists()
stock,meter=(b.resolve(strict=True) for b in (a.stock,a.meter))
stock_hash,meter_hash=sha(stock),sha(meter)
assert stock_hash!=meter_hash
mappings={}
for label,path in zip(('large_jsonl','small_jsonl','sqlite'),a.fixtures):
    r=path.resolve(strict=True)
    m=json.loads((r/'fixture.json').read_text())
    j=r/m['journal']
    assert sha(j)==m['journal_sha256'] and stock_hash==m['worker_sha256']
    assert m['backend']==('sqlite' if label=='sqlite' else 'jsonl')
    assert m['pilot']==(label=='small_jsonl')
    if label!='sqlite':
        assert (m['journal_bytes']>=1024*1024)==(label=='large_jsonl')
    target=r/m['session_dir']
    os.environ['TMPDIR']=str(r/'temp')

    def trial(arm):
        if arm=='default':
            os.environ['R61_FORCE_DEFAULT_STAGE']='1'
        else:
            os.environ.pop('R61_FORCE_DEFAULT_STAGE',None)
        with Client(stock if arm=='stock' else meter,m['backend'],host_features=('display_projection',)) as cli:
            d=cli.call('open',path=str(target))['descriptor']
            pr=cli.call('open_display_snapshot',session=d['session'])['projection']
            snapshot=pr['snapshot']
            sid=snapshot['snapshot_id'].encode()
            def frame():
                b=cli.last_raw
                assert b.count(sid)==1 and len(sid)==36
                return dict(frame_bytes=len(b),sha256=hashlib.sha256(
                    b.replace(sid,b'00000000-0000-0000-0000-000000000000')).hexdigest())
            assert snapshot['revision']==m['canonical_snapshot_revision']
            assert snapshot['content_sha256']==m['canonical_digest']
            assert len(pr['state']['conversation']['messages'])==m['canonical_active']
            wire=dict(projection=frame(),pages=[])
            after=0; seq=0
            while after is not None:
                page=cli.call('read_display_records',snapshot=snapshot,after_seq=after,limit=64)['page']
                assert page['snapshot']==snapshot
                for record in page['records']:
                    seq+=1
                    assert record['session_seq']==seq
                next_after=page['next_after_seq']
                wire['pages'].append(dict(after=after,next=next_after,records=len(page['records']),**frame()))
                after=next_after
            assert seq==m['exact_fresh_canonical_read_records']
            cli.call('release_snapshot',snapshot=snapshot)
        assert sha(j)==m['journal_sha256']
        assert len(cli.reports)==int(arm!='stock')
        if not cli.reports:
            return wire,None
        stream_calls,stream_chars,finish_calls,finish_chars,stage_bytes,capacity=cli.reports[0]
        assert stream_chars+finish_chars==stage_bytes
        assert stream_calls>0 and finish_calls==1 and finish_chars>0
        return wire,dict(stream_syscw=stream_calls,finish_syscw=finish_calls,
            total_syscw=stream_calls+finish_calls,stream_wchar=stream_chars,
            finish_wchar=finish_chars,staged_bytes=stage_bytes,capacity=capacity)

    oracle,_=trial('stock')
    counts={'default':[],'candidate':[]}
    for arms in [('default','candidate'),('candidate','default')]:
        for arm in arms:
            wire,report=trial(arm)
            assert wire==oracle,(label,arm)
            counts[arm].append(report)
    base,cand=(v[0] for v in counts.values())
    assert all(v[0]==v[1] for v in counts.values()),(label,counts)
    assert base['staged_bytes']==cand['staged_bytes']
    if label=='large_jsonl':
        assert cand['capacity']==65536 and base['capacity']==8192
        assert cand['total_syscw']*2<base['total_syscw'], (label,counts)
    else:
        assert cand==base,(label,counts)
    mappings[label]={'source_sha256':m['journal_sha256'],'source_bytes':m['journal_bytes'],
        'rows_visible':m['rows'],'canonical_records':m['exact_fresh_canonical_read_records'],
        'raw_pairs':counts,'wire_reference':oracle}
a.out.write_text(json.dumps({
    'method':'Linux own worker /proc/self/io syscw/wchar, stream and final flush separately; catalog/source/SDK writes outside',
    'normalized':'only the 36-byte random snapshot_token in raw complete response frames',
    'worker_hashes':{'stock':stock_hash,'meter':meter_hash},'fixtures':mappings
},indent=2)+'\n')
