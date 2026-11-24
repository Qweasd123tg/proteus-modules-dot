"""Independently recheck raw records written by the authenticated source-lift."""
import json, hashlib
from pathlib import Path
d=Path(__file__).resolve().parent
if d.name == 'packet': d=d.parent
bench=d.parent.parent/'bench'
out={}
k_canon=['canonical_messages','canonical_parts','canonical_text','canonical_other']
for mode in ['default','preserve']:
 out[mode]={}
 for category,count in [('controls',58),('scale',2)]:
  raw={}
  for arm in ['orig','new']:
   p=bench/f'{arm}-{mode}-{category}.jsonl';b=p.read_bytes()
   lines=list(map(json.loads,b.splitlines()))
   assert len(lines)==count==len({json.dumps(r['case'],sort_keys=True)for r in lines})
   raw[arm]=(hashlib.sha256(b).hexdigest(),{json.dumps(r['case'],sort_keys=True):r for r in lines})
  a,b=raw['orig'][1],raw['new'][1]
  assert set(a)==set(b)
  for key in a:
   x,y=a[key],b[key]
   for field in ['case','headersha','ops','opsha','outcome','pages','pagesha','phases','staged']:
    assert x[field]==y[field],(mode,category,key,field,x[field],y[field])
  out[mode][category]={'paired_parity_cases':count,'raw_sha256':{arm:v[0] for arm,v in raw.items()}}
  if category=='scale':
   for key in a:
    x,y=a[key],b[key]
    assert set(x['life'])==set(y['life'])
    assert x['life']['before_conversation']==y['life']['before_conversation']
    assert x['life']['named_page_probe']==y['life']['named_page_probe']
    n=lambda obj,fields:sum(obj['bytes'] for k,obj in obj.items() if k in fields)
    ax,ay=x['life']['before_display'],y['life']['before_display']
    before,after=n(ax,k_canon),n(ay,k_canon)
    assert before==(34088890 if mode=='default' else 38088890) and after==0
    owned=n(ax,['rendered_owned','rendered_rows'])
    assert owned==n(ay,['rendered_owned','rendered_rows'])
    prefix=n(ax,{k for k in ax if k.startswith('prefix')}|{'history_digests'})
    assert prefix==n(ay,{k for k in ax if k.startswith('prefix')}|{'history_digests'})
    out[mode][x['case']['route']]=dict(before_display_canonical_bytes_before=before,before_display_canonical_bytes_after=after,unchanged_before_display_rendered_bytes=owned,unchanged_before_display_prefix_and_digest_bytes=prefix)
receipt={'scope':'Independent check over authenticated source lift, synthetic backend and allocator generation tags, not full-Core/worker/GUI/RSS.', 'modes':out}
(d/'packet/independent-lift-check.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
