"""Verify sealed R62 count outputs independently without starting workers."""
import json
from pathlib import Path
import sys

d=Path(__file__).resolve().parent
paths=sys.argv[1:] or ('main-counts.json','composed-counts.json')
hashes=set()
wire=None
for f in paths:
    r=json.loads((d/f).read_text())
    assert (r['files'],r['files_at_most_64k'],r['bytes'])==(320,317,8301484)
    assert r['source_sha256']=='e00e71759cfda4f4982c5d2f9f4790bed78a7fb0e8cab22e0e96d03c8dbf4c61'
    assert r['stock_sha256']=='e3fd78af7bd2d8af3f86de719639f4cd7872bfe402da03aa6030471edc921502'
    assert r['meter_sha256'] not in hashes and r['meter_sha256']!=r['stock_sha256']
    hashes.add(r['meter_sha256'])
    assert r['order']==['default,hint','hint,default']
    if wire is None: wire=r['wire_reference']
    assert wire==r['wire_reference']
    assert len(wire['hit_response_sha256'])==len(wire['hit_etags'])==320
    assert all(len(x)==64 for x in wire['hit_response_sha256']+wire['hit_etags'])
    pairs=[]
    for old,new in zip(r['raw']['default'],r['raw']['hint']):
        assert old['hit_scope']['requests']==new['hit_scope']['requests']==320
        assert old['actual_sdk_worker_rchar']==new['actual_sdk_worker_rchar']==8714601
        assert old['missing_scope']==new['missing_scope']
        pairs.append((old['actual_sdk_worker_syscr']-new['actual_sdk_worker_syscr'],
                      old['hit_scope']['allocation_calls']-new['hit_scope']['allocation_calls'],
                      old['hit_scope']['allocation_requested_bytes']-new['hit_scope']['allocation_requested_bytes']))
    assert len(pairs)==2 and pairs==[(2535,2538,3078621)]*2
    print(f,pairs,'PASS raw frames, file set, counters and absent/matching-source controls')
