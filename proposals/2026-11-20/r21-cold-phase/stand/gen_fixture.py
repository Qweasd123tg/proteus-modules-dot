"""Generate once with real external JSONL v3 process; clone canonical fixture for each measured arm."""
import argparse,json
from pathlib import Path
from rpc import Fixture, Worker, msg, uid

def seed(worker,config,cwd,sid,rows):
    f=Fixture.__new__(Fixture); f.w=worker
    desc=worker.do('create',config_root=str(config),workspace_path=str(cwd),session_id=uid(sid),parent_session_id=None)['descriptor']
    f.session=desc['session']; f.acquire()
    for start in range(0,rows,100):
        chunk=[]
        for i in range(start,min(start+100,rows)):
            v=msg(i,label(sid,i))
            v["parts"][0]["part_id"]=uid(1000000+i)
            if i%2: v["role"]="Assistant";v["parts"][0]["provenance"]="model"
            chunk.append(v)
        f.write(chunk)
    if rows>100:
        assert len(chunk)==100
        f.write(chunk,"replace",dict(changed=True,user_message_replacements=[],reason="archive-tail",input_messages=rows,output_messages=100,summary_source="synthetic-bounds",metadata=None))
    f.release()
    return Path(desc['local_path'])

def label(sid,i):
    return f"synthetic-{sid}-{i:06d}: "+"Фиктивная строка журнала. "*3


def generate(root,worker,archives,rows):
    if rows<100 or rows%100 or archives<4: raise ValueError("rows must be multiples of 100, archives >= 4")
    root=root.resolve()
    root.mkdir(exist_ok=False,parents=True)
    cfg=root/'config';cwd=root/'work';cfg.mkdir();cwd.mkdir()
    w=Worker(worker.resolve(strict=True),'jsonl')
    try:
        active=seed(w,cfg,cwd,9,100)
        dirs=[seed(w,cfg,cwd,100+i,rows if i<4 else 100) for i in range(archives)]
    finally:w.close()
    manifest=dict(archives=archives,rows=rows,active=str(active.relative_to(cfg)),dirs=[str(d.relative_to(cfg)) for d in dirs])
    (root/'archives.json').write_text(json.dumps(manifest))
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ('root','worker'):p.add_argument('--'+arg,type=Path,required=True)
    p.add_argument('--archives',type=int,default=100);p.add_argument('--rows',type=int,default=125000)
    a=p.parse_args();generate(a.root,a.worker,a.archives,a.rows)
