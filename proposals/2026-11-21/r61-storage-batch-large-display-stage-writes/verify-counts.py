"""Check the closed R61 count packet. Executes no worker."""
import json
import sys
from pathlib import Path

p=Path(__file__).resolve().parent
data=json.loads((p/(sys.argv[1] if len(sys.argv)>1 else 'counts.json')).read_text())
assert data['worker_hashes']['stock']=='e3fd78af7bd2d8af3f86de719639f4cd7872bfe402da03aa6030471edc921502'
assert data['worker_hashes']['meter']!=data['worker_hashes']['stock']
fixtures=data['fixtures']
assert fixtures['large_jsonl']['source_sha256']=='e00e71759cfda4f4982c5d2f9f4790bed78a7fb0e8cab22e0e96d03c8dbf4c61'
answer={
    'large_jsonl': ((6442,803),52568667,(8192,65536),1251,20),
    'small_jsonl': ((57,57),461033,(8192,8192),11,1),
    'sqlite': ((46,46),372072,(8192,8192),20,1),
}
assert set(answer)==set(fixtures)
for label,((old,new),stage_bytes,(ca,cb),records,pages) in answer.items():
    x=fixtures[label]
    assert x['canonical_records']==records
    for arm,calls,cap in [('default',old,ca),('candidate',new,cb)]:
        y=x['raw_pairs'][arm]
        assert len(y)==2 and y[0]==y[1]
        for r in y:
            assert r['finish_syscw']==1
            assert r['stream_syscw']+r['finish_syscw']==r['total_syscw']==calls
            assert r['stream_wchar']+r['finish_wchar']==r['staged_bytes']==stage_bytes
            assert r['capacity']==cap
    w=x['wire_reference']['pages']
    assert len(w)==pages and sum(page['records'] for page in w)==records
    assert w[0]['after']==0 and w[-1]['next'] is None
    assert all(a['next']==b['after'] for a,b in zip(w,w[1:]))
    print(label, old,new,stage_bytes,ca,cb,records,pages)
print('PASS exact duplicated counts, staged bytes and complete SDK coverage')
