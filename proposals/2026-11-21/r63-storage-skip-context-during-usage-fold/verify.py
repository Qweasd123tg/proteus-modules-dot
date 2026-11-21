"""Validate R63 native count receipt without replaying a fixture."""
from pathlib import Path
from collections import defaultdict
import json
import re

here=Path(__file__).resolve().parent
text=(here/'measure-final.log').read_text()
groups=defaultdict(list)
rows=re.findall(r'R63 scope=(jsonl|sqlite) turns=(\d+) records=(\d+) full=(true|false) alloc_calls=(\d+) alloc_bytes=(\d+) context_visits=(\d+) serialized_sha256=([0-9a-f]{64})',text)
assert len(rows)==16
assert 'test result: ok. 2 passed; 0 failed' in text
assert 'r63_usage_replay_keeps_the_same_failed_read_and_stale_revision ... ok' in text
for scope,turns,records,full,calls,requested,context,hexvalue in rows:
    groups[(scope,int(turns))].append(dict(records=int(records),full=full=='true',alloc_calls=int(calls),
        alloc_bytes=int(requested),context_visits=int(context),serialized_sha256=hexvalue))
report={}
for (scope,turns),items in groups.items():
    assert [v['full'] for v in items]==[True,False,False,True]
    assert len({v['serialized_sha256'] for v in items})==1
    assert all(v['records']==(1620 if turns else 0) for v in items)
    assert all(v['context_visits']==(v['records'] if v['full'] else 0) for v in items)
    pairs=[]
    for large,small in ((items[0],items[1]),(items[3],items[2])):
        calls=large['alloc_calls']-small['alloc_calls']
        bytes_saved=large['alloc_bytes']-small['alloc_bytes']
        if turns: assert calls>0 and bytes_saved>0
        else: assert calls==bytes_saved==0
        pairs.append(dict(calls=calls,bytes=bytes_saved,percent=100*bytes_saved/large['alloc_bytes']))
    report[f'{scope}-{turns}']=dict(read_order=['full','usage','usage','full'],raw=items,paired_saved=pairs)
print(json.dumps(report,indent=2))
