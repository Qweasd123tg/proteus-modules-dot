"""Require the entire two-arm actual route matrix, not just successful exit."""
import json,sys,hashlib
from pathlib import Path
def check(raw):
 rows=[json.loads(line) for line in raw.splitlines()]
 expected={}
 for c in ['stock','candidate']:
  for n in [0,1,5000,50000]:
   for m in ['Lease','Good']:
    expected[(c,'resident-'+m,n)]=[] if m=='Lease' else ['open','release']
  for m in ['WrongResponse','WrongSession','WorkerError','ReleaseError']:
   expected[(c,'resident-'+m,1)]=['open','release'] if m=='ReleaseError' else ['open']
  for m in ['Good','WorkerError','WrongResponse','WrongSession','ReleaseError','WrongConversation']:
   expected[(c,'nonresident-'+m,1)]=['open'] if m in ['WorkerError','WrongResponse','WrongSession'] else ['open','read','release']
  for ph in ['history','context','writer','granted-before-repoll']:
   expected[(c,'cancel-'+ph+'-then-retry',1)]=['open','release']
  for k in ['cancel-granted-queued-sibling-resumes','no-store','nonresident-no-store']:
   expected[(c,k,1)]=[]
 seen={}
 for d in rows:
  assert set(d)=={'arm','case','rows','events','validated'} and d['validated'] is True
  k=d['arm'],d['case'],d['rows'];assert k not in seen,k
  seen[k]=d['events']
 assert seen==expected,(seen.keys()^expected.keys(),set(k for k in seen if seen[k]!=expected[k]))
 return {'sha256':hashlib.sha256(raw).hexdigest(),'cases':len(seen),'per_arm':len(seen)//2,'max_resident_rows':50000,'status':'PASS'}
if __name__=='__main__':
 print(json.dumps(check(Path(sys.argv[1]).read_bytes()),sort_keys=True))
