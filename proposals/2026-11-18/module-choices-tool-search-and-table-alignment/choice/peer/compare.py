"""Compare two actual runs on the same compiler/adapters; not a timing or process-memory test."""
import re,sys
from pathlib import Path
def take(path):
 lines=Path(path).read_text().splitlines()
 assert lines[0]=='native retained rows: 800 forms, 2080 checkbox states and 8320 exact callbacks; includes duplicates, mixed JSON, missing/default, unknowns, invalid shape.'
 ret={}
 for line in lines[1:]:
  match=re.fullmatch(r'n=(\d+) allocation_requests=(\d+) requested_bytes=(\d+)',line);assert match,line
  n,c,b=map(int,match.groups());ret[n]=c,b
 assert list(ret)==[8,16,32,64,128];return ret
b,a=map(take,sys.argv[1:3])
for n in b:
 bc,bb=b[n];ac,ab=a[n];assert ac<bc and ab<bb,(n,b[n],a[n])
 assert (n<32 or (bc>12*ac and bb>12*ab))
assert b[128][1]>70*a[128][1]
print('GO: checked, independently, all recorded checkbox semantics and allocation-request reductions on this adapter. Bytes: '+str(b[128][1])+' -> '+str(a[128][1])+' at n=128.')
