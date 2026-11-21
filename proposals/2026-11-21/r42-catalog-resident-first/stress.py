"""Optional boundary extension. Run with same CLI as profile.py, --candidate required."""
from pathlib import Path
import json, time, re
exec((Path(__file__).with_name("profile.py").read_text().rsplit("with args.output.open('w') as file:",1)[0]))
def stress(tmp,b,file):
    global binary
    cfg=tmp/'cfg'; A=tmp/'A'; B=tmp/'B'; hot=tmp/'small'
    for d in [cfg,A,B,hot]: d.mkdir()
    n=2058; sets=[range(1,1026),range(1026,2051),range(2051,2059)]
    binary=args.binary.resolve(); locs=[]; sessions=[]
    with Client(b) as c:
        for ws,ids in zip((A,B,hot),sets):
            for id in ids:
                s,p=setup(c,cfg,ws,id-1,1); locs.append(p);sessions.append(s)
        measure(c,cfg,None,range(1,n+1),n,b,'prepare','setup',0,file)
    for label,exe in [('base',args.binary),('cand',args.candidate)]:
        binary=exe.resolve()
        with Client(b) as c:
            for stage,ws,ids in [('cold-A',A,sets[0]),('repeat-A',A,sets[0]),('switch-B',B,sets[1]),('repeat-B',B,sets[1]),('hot-before',hot,sets[2]),('global',None,range(1,n+1)),('hot-after',hot,sets[2]),('global2',None,range(1,n+1)),('hot-after2',hot,sets[2])]:
                measure(c,cfg,ws,ids,n,b,stage,label,0,file)
    # Independent final cold process: absent and malformed indexes require two true replays.
    binary=args.candidate.resolve()
    locs[-1].joinpath('.storage-catalog-v1.json').unlink()
    locs[-2].joinpath('.storage-catalog-v1.json').write_bytes(b'{bad')
    with Client(b) as c:
        counts=measure(c,cfg,None,range(1,n+1),n,b,'missing-and-corrupt-sidecars','cand',0,file)
        assert counts==[0,n-2,2]
        assert all(json.loads(locs[i].joinpath('.storage-catalog-v1.json').read_bytes())['checksum'] for i in [-1,-2])
        # Alias paths project the same canonical session and must not disappear.
        alias=locs[-1].parent/'r42-alias'
        alias.symlink_to(locs[-1],target_is_directory=True)
        alias_rows=[]
        for binpath in [args.binary,args.candidate]:
            binary=binpath.resolve()
            with Client(b) as probe:
                for _ in range(2):
                    rows=probe.call('list',config_root=str(cfg),workspace_path=None,audit=False)['sessions']
                    probe.logfile.readline()
                assert len(rows)==n+1
                duplicate=[r for r in rows if r['descriptor']['session']['session_id']==u(n)]
                assert len(duplicate)==2 and duplicate[0]==duplicate[1]
                alias_rows.append(rows)
        assert alias_rows[0]==alias_rows[1]
        alias.unlink()
        print(b,'stable oversized alias catalog: all 2059 ordered rows equal between binaries',flush=True)
        # Mutate an actually resident row from another fresh worker. Its sidecar now has stale stamps.
        opened=c.call('open_snapshot',session=sessions[-1])['snapshot'];c.call('release_snapshot',snapshot=opened)
        with Client(b) as writer:
            ans=writer.call('acquire_writer',session=sessions[-1]);lease=ans['lease'];rev=ans['revision']
            writer.call('commit',commit=dict(lease=lease,operation_id=u(9_000_001),expected=rev,timestamp_ms=9999,attribution=dict(execution_id=None,thread_id=u(9_000_002),turn_id=None),entry=dict(kind='history_mutated',payload=dict(previous_revision=1,new_revision=2,mutation='append',messages=[dict(id=u(9_000_003),role='User',phase=None,parts=[dict(part_id=u(9_000_004),provenance='user',scope='conversation',payload={'Text':{'text':'new committed row'}})],name=None,tool_call_id=None,metadata={})],compaction=None,tool_results=[]))))
            writer.call('release_writer',lease=lease)
        resp=c.call('list',config_root=str(cfg),workspace_path=None,audit=False);rows=resp['sessions'];log=c.logfile.readline().decode().strip()
        assert len(rows)==n and [x['message_count'] for x in rows if x['descriptor']['session']['session_id']==u(n)]==[4]
        assert [(x['descriptor']['updated_at_ms'],x['descriptor']['session']['key']) for x in rows]==sorted([(x['descriptor']['updated_at_ms'],x['descriptor']['session']['key']) for x in rows],reverse=True)
        # Invalid canonical metadata after a warm read must not be returned from memory.
        locs[-1].joinpath('session.json').write_bytes(b'{bad')
        resp=c.call('list',config_root=str(cfg),workspace_path=None,audit=False)
        rows=resp['sessions'];c.logfile.readline()
        assert len(rows)==n-1 and not any(x['descriptor']['session']['session_id']==u(n) for x in rows)
        q=c.send('list',config_root=str(cfg),workspace_path=None,audit=True)
        raw=json.loads(c.p.stdout.readline());assert raw['id']==q and 'error' in raw,raw
        print(b,'MISSING CORRUPT SIDECAR REPLAY=2; DIRECT READ, EXTERNAL APPEND 3->4, CORRUPT ID OMIT/AUDIT ERROR OK',flush=True)
with args.output.open('w') as file:
    for b in ['jsonl','sqlite']:
        with tempfile.TemporaryDirectory(dir=args.fixture_dir) as tmp:stress(Path(tmp).resolve(),b,file)
