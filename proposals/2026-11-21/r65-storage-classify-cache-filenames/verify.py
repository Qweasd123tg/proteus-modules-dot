"""Verify sealed R65 operation/allocation evidence, no build or replay."""
from pathlib import Path
import ast
import json
import re

here=Path(__file__).resolve().parent
s=(here/'native-and-measure.log').read_text()
pattern=r'R65 old=(true|false) names=(\d+) name_bytes=(\d+) lossy_input_bytes=(\d+) basename_evaluations=(\d+) stat_calls=(\d+) allocs=(\d+) alloc_requested=(\d+)'
raw=[]
for old,names,name_bytes,lossy,basename,stat,calls,requested in re.findall(pattern,s):
    old=old=='true'
    r=dict(old=old,names=int(names),name_bytes=int(name_bytes),
           lossy_input_bytes=int(lossy),basename_evaluations=int(basename),
           stat_calls=int(stat),allocation_calls=int(calls),allocation_requested=int(requested))
    assert (r['names'],r['name_bytes'],r['stat_calls'])==(52320,4326080,51360)
    assert r['lossy_input_bytes']==(4326080 if old else 0)
    assert r['basename_evaluations']==(51360 if old else 320)
    assert (r['allocation_calls'],r['allocation_requested'])==(107324,15954784)
    raw.append(r)
assert [r['old'] for r in raw]==[True,False,False,True]
row=re.search(r'R65 unix_legacy_file_control old=(\[[^\]]+\]) new=(\[[^\]]+\])',s)
assert row
a,b=(ast.literal_eval(t) for t in row.groups())
assert (a,b)==([2,32,32,1,1,11,417],[2,32,0,1,1,7,321])
assert 'test result: ok. 66 passed; 0 failed; 1 ignored' in s
assert 'cache_name_checks_leave_ascii_boundary_behavior_exact ... ok' in s
assert 'cache_name_filter_preserves_quota_keep_and_normal_missing_directory_error ... ok' in s
print(json.dumps(dict(sweeps_per_arm=320,fixture='320 exact R59 cache-doc copies + three ordinary ignored names',
  raw_under_quota=raw, unix_legacy_control=dict(old=a,new=b), disclaimer='structural enabled source work, no time/syscall-instruction attribution'),indent=2))
