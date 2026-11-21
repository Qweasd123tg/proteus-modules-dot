#!/usr/bin/env python3
"""Capture only real stock ListCandidates descriptors of fresh synthetic sessions."""
from pathlib import Path
import hashlib,json,os,tempfile,sys
from rpc import Client,setup
worker=Path(sys.argv[1]).resolve(strict=True)
destination=Path(sys.argv[2]).resolve()
assert not destination.exists()
destination.mkdir()
print('worker SHA256',hashlib.sha256(worker.read_bytes()).hexdigest())
with tempfile.TemporaryDirectory(prefix='r53-ranked-') as temp:
    root=Path(temp)
    home=root/'home';home.mkdir()
    os.environ.clear()
    os.environ.update(dict(HOME=str(home),XDG_CONFIG_HOME=str(root),PROTEUS_CONFIG_HOME=str(root),TMPDIR=str(root),PATH='/usr/bin:/bin'))
    for backend in ['jsonl','sqlite']:
        cfg=root/backend;cfg.mkdir()
        ws=cfg/'workspace';ws.mkdir()
        with Client(worker,backend) as writer:
            dirs=[setup(writer,cfg,ws,i,k=1,size=16) for i in range(128)]
        journal=[d/f'journal.{backend}' for d in dirs]
        assert all(p.is_file() for p in journal)
        for tied in (False,True):
            for i,p in enumerate(journal):
                t=1700000000+(0 if tied else i)
                os.utime(p,ns=(t*10**9,)*2)
            with Client(worker,backend) as reader:
                reply=reader.call('list_candidates',config_root=str(cfg),workspace_path=str(ws))
                assert reply['result']=='candidates'
                out=reply['sessions']
                assert len(out)==len(dirs)
            # Normalize metadata unrelated to Core comparator, preserve equivalent
            # lexical path suffixes, receipt order, tie classes and sizes of rows.
            for index,row in enumerate(out):
                assert row['parent_session_id'] is None
                row['workspace_path']='/fixture/project'
                row['local_path']='/synthetic/sessions/'+Path(row['local_path']).name
                row['record_location']=row['local_path']+'/journal.'+backend
                row['session']['key']=f'opaque-provider-key-{index:04d}'
            name=f'real-{backend}-'+('tied' if tied else 'distinct')
            (destination/(name+'.json')).write_text(json.dumps(out,ensure_ascii=False)+'\n')
            print(name,'captured',len(out),'rows')
