#!/usr/bin/env python3
"""Seed fresh PRIVATE canonical synthetic snapshots using real baseline storage v2."""
from pathlib import Path
from collections import Counter
import argparse, hashlib, json, os
from rpc import Client, u

PROFILES={
    'sqlite1k': {'backend':'sqlite','rows':1000,'batch':50,'canonical_active':1000,'text':'r50-short'},
    'jsonl125k': {'backend':'jsonl','rows':125000,'batch':100,'canonical_active':100,'text':'r12-archive'},
}
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def expected_text(p,i,n):
    if p['text']=='r50-short':return f'row {i:05}: '+('x'*96)
    active=p['canonical_active']
    label=f'active-{i-(n-active):04}' if i>=n-active else f'archive-{i:04}'
    return label+': ' + 'Фиктивная строка журнала. '*3
def message(p,i,n):
    return dict(id=u(101+i*2),role='User' if i%2==0 else 'Assistant',phase=None,
        parts=[dict(part_id=u(102+i*2),provenance='user' if i%2==0 else 'model',
          scope='conversation',payload={'Text':{'text':expected_text(p,i,n)}})],
        name=None,tool_call_id=None,metadata={})
def seed(worker,root,p):
    ws=root/'project'
    cfg=root/'profile'
    for d in [ws,cfg,root/'home',root/'temp',root/'runtime']: d.mkdir(exist_ok=False)
    clean=dict(PATH='/usr/bin:/bin',HOME=str(root/'home'),TMPDIR=str(root/'temp'),
        XDG_DATA_HOME=str(root/'home'),XDG_CONFIG_HOME=str(cfg),XDG_STATE_HOME=str(root/'home'),
        PROTEUS_HOME=str(root/'runtime'),PROTEUS_CONFIG_HOME=str(cfg))
    os.environ.clear();os.environ.update(clean)
    n=p['rows']; b=p['batch'];k=p['canonical_active']
    with Client(worker,p['backend']) as s:
        desc=s.call('create',config_root=str(cfg),workspace_path=str(ws),
                    session_id=u(1),parent_session_id=None)['descriptor']
        session=desc['session']; begin=s.call('acquire_writer',session=session)
        lease=begin['lease']; rev=begin['revision']; asserts=0
        def commit(offset,mutation,messages,report=None):
            nonlocal rev,asserts
            entry=dict(kind='history_mutated',payload=dict(previous_revision=rev['history_revision'],
                new_revision=rev['history_revision']+1,mutation=mutation,messages=messages,
                compaction=report,tool_results=[]))
            out=s.call('commit',commit=dict(lease=lease,operation_id=u(10000001+offset),expected=rev,
                timestamp_ms=1000+offset,attribution=dict(execution_id=None,thread_id=u(99),turn_id=None),entry=entry))
            rev=out['ack']['revision']; asserts+=1
            assert rev['history_revision']==asserts
        for off in range(0,n,b):
            commit(off,'append',[message(p,i,n) for i in range(off,min(off+b,n))])
        if k<n:
            report=dict(changed=True,user_message_replacements=[],reason='Synthetic tail compaction',
                input_messages=n,output_messages=k,original_token_estimate=None,output_token_estimate=None,
                trigger_tokens=None,summary_source='history-scale-fixture-tail',skipped_reason=None,
                summary=None,metadata=None)
            commit(n,'replace',[message(p,i,n) for i in range(n-k,n)],report)
        s.call('release_writer',lease=lease)
    session_dir=Path(desc['local_path']); assert session_dir.is_relative_to(cfg)
    journal=session_dir/('journal.sqlite' if p['backend']=='sqlite' else 'journal.jsonl')
    assert journal.exists() and not (session_dir/'journal.sqlite-wal').exists()
    assert not list(session_dir.glob('.storage-cache-*'))
    # New baseline worker strictly verifies canonical records over the ordinary
    # pinned read contract. Count only; do not make a duplicate payload archive.
    expected_sha=sha(journal); counts=Counter()
    with Client(worker,p['backend']) as s:
        snapshot=s.call('open_snapshot',session=session)['snapshot']
        assert snapshot['revision']==rev
        cur=0
        while cur is not None:
            page=s.call('read_records',snapshot=snapshot,after_seq=cur,limit=64)['page']
            assert page['snapshot']==snapshot
            for r in page['records']:
                i=counts['records']; item=r['entry']; assert r['session_seq']==i+1
                assert item['kind']=='history_mutated'
                v=item['payload']; expected_mut='append'
                if i*b<n: indexes=range(i*b,min((i+1)*b,n))
                else:
                    expected_mut='replace'; indexes=range(n-k,n)
                    assert v['compaction']['input_messages']==n and v['compaction']['output_messages']==k
                assert v['mutation']==expected_mut and v['previous_revision']==i
                assert v['messages']==[message(p,j,n) for j in indexes]
                counts['records']+=1
            cur=page['next_after_seq']
        s.call('release_snapshot',snapshot=snapshot)
    assert counts['records']==asserts and sha(journal)==expected_sha
    assert not list(session_dir.glob('.storage-cache-*'))
    m=dict(p, journal_bytes=journal.stat().st_size,journal_sha256=expected_sha,
        canonical_snapshot_revision=rev,canonical_digest=snapshot['content_sha256'],
        worker_sha256=sha(worker),workspace='project',session_dir=str(session_dir.relative_to(root)),
        app_profile='profile/probe.toml',journal=str(journal.relative_to(root)),
        exact_fresh_canonical_read_records=asserts)
    (root/'fixture.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n')
    return {key:m[key] for key in ('rows','canonical_active','journal_bytes','journal_sha256','exact_fresh_canonical_read_records')}
def config_for(worker,backend):
    return '[modules]\nsession_storage='+json.dumps(backend)+'\n[components.store]\ncommand='+json.dumps(str(worker))+f'\n[components.store.exports.session_storage.{backend}]\n'
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('profile',choices=PROFILES);ap.add_argument('seed_worker',type=Path)
    ap.add_argument('directory',type=Path);ap.add_argument('--pilot-rows',type=int,
        help='preflight only: altered corpus must not enter measurement')
    a=ap.parse_args(); root=a.directory.resolve()
    assert not root.exists(), 'choose a new output directory'
    root.mkdir(mode=0o700,parents=False)
    p=dict(PROFILES[a.profile],profile=a.profile,pilot=a.pilot_rows is not None)
    if a.pilot_rows:
        assert p['canonical_active']<a.pilot_rows<p['rows'] and a.pilot_rows%p['batch']==0
        p['rows']=a.pilot_rows
    worker=a.seed_worker.resolve(strict=True)
    report=seed(worker,root,p)
    (root/'profile/probe.toml').write_text(config_for(worker,p['backend']))
    print(json.dumps(report))
