import argparse,json,hashlib
from pathlib import Path
from rpc import *
d=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('worker',type=Path);p.add_argument('new_fixture',type=Path);a=p.parse_args()
root=a.new_fixture.resolve();root.mkdir(exist_ok=False)
binary=a.worker.resolve()
f=Fixture(binary,'jsonl',root)
n=125000
r=None
for base in range(0,n,100):
    rows=[msg(i,f'{i:06}: '+'Фиктивная строка журнала. '*3) for i in range(base,base+100)]
    # Globally distinct message and part UUIDs.
    for i,m in enumerate(rows,base):m['parts'][0]['part_id']=uid(10000000+i)
    f.write(rows);r=rows
# Last operation retains only the active 100; no compaction report is needed.
f.write(r,'replace')
f.release();f.w.close()
j=f.dir/'journal.jsonl';session=f.session
(root/'info.json').write_text(json.dumps({'file':str(j),'session':session,'sha256':hashlib.sha256(j.read_bytes()).hexdigest(),'bytes':j.stat().st_size}))
