import json,re,sys
from pathlib import Path
pattern=r'^width=(\d+) mode=(\w+) alloc_bytes=(\d+) alloc_calls=(\d+) moved=(true|false)$'
def rows(log):
    s=Path(log).read_text()
    assert 'invalid request rejected before dispatch' in s
    hits=re.findall(pattern,s,re.M)
    assert len(hits)==7
    return {(int(w),m):(int(n),int(c),mv=='true') for w,m,n,c,mv in hits}
b,a=map(rows,sys.argv[1:])
assert b.keys()==a.keys()=={(n,'Some') for n in (1024,1<<20,8<<20)}|{(8<<20,'Pending')}|{(1024,m) for m in ('Duplicate','Unknown','None')}
out=[]
for (width,mode),baseline in b.items():
    after=a[width,mode];assert not baseline[2] and after[2]
    if width>=1<<20:assert baseline[0]-after[0]>=width and after[0]<1<<17
    out.append(dict(width=width,mode=mode,before_bytes=baseline[0],after_bytes=after[0],before_calls=baseline[1],after_calls=after[1],same_input_allocation_before=baseline[2],same_input_allocation_after=after[2]))
print(json.dumps(out, indent=2))
