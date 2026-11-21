"""Check measured report independently, no loads, builds, or elapsed trials."""
import json
from pathlib import Path
from statistics import median

root=Path(__file__).resolve().parent
expected='e00e71759cfda4f4982c5d2f9f4790bed78a7fb0e8cab22e0e96d03c8dbf4c61'
for filename,composition in [('main-alloc.json','main'),('composed-alloc.json','after-256')]:
    data=json.loads((root/filename).read_text())
    assert data['canonical_sha256']==expected and data['backend']=='jsonl'
    assert data['composition']==composition
    assert data['binary_sha256']['diagnostic']!=data['binary_sha256']['reference']
    assert data['comparisons']==2 and data['orders']==['fresh,scratch','scratch,fresh']
    raw=data['raw']
    deltas=[[old-new for old,new in zip(old,new)] for old,new in zip(raw['fresh'],raw['scratch'])]
    assert all(all(x>0 for x in diff) for diff in deltas)
    assert deltas==data['paired_saved']
    assert [median(col) for col in zip(*deltas)]==data['saved']
    page=data['exact_normalized_wire_reference']['pages']
    assert len(page)==20 and sum(p['records'] for p in page)==1251
    assert page[0]['after']==0 and page[-1]['next'] is None
    assert all(a['next']==b['after'] for a,b in zip(page,page[1:]))
    print(composition, data['paired_saved'], data['saved'])
print('PASS counts, saved allocations in both orders; complete canonical/SDK scope')
