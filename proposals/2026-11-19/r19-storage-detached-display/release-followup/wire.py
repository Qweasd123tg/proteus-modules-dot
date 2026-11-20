"""Deterministic release of an already staged display snapshot vs a held SQLite read."""
import ctypes, hashlib, json, os, queue, select, sqlite3, sys, tempfile, threading, time
from pathlib import Path
from rpc import Fixture, msg, uid
worker=Path(sys.argv[1]).resolve(strict=True)
mode=sys.argv[2]
assert mode in ('open_snapshot','open_display_snapshot')

def fd_keys(pid):
    keys=set()
    for f in Path(f'/proc/{pid}/fd').iterdir():
        try:
            path=os.readlink(f)
            st=f.stat()
            if path.endswith(' (deleted)') and st.st_size>0:
                keys.add((st.st_dev,st.st_ino,st.st_size))
        except FileNotFoundError: pass
    return keys

def send(w, operation, **fields):
    rid=f"h:1:{w.seq}"; w.seq+=1
    body=dict(export=dict(slot="session_storage",module_id="sqlite"),
              lineage=dict(root_invocation_id=rid,parent_invocation_id=None,depth=0),
              params=dict(operation=operation, **fields))
    w.process.stdin.write(json.dumps(dict(jsonrpc="2.0",id=rid,method="execute",params=body)).encode()+b'\n')
    w.process.stdin.flush()
    return rid

def checkpoint(db):
    with sqlite3.connect(db,timeout=0) as c:
        return c.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()

def run(root):
    a=Fixture(str(worker),'sqlite',root); w=a.w; fd=-1; lk=None
    try:
        a.write([msg(1,"pinned history")])
        b=Fixture.__new__(Fixture);b.w=w
        desc=w.do('create',config_root=str(root/'config'),workspace_path=str(root/'work'),session_id=uid(8),parent_session_id=None)['descriptor']
        b.session=desc['session'];b.acquire();b.write([msg(3,'held read')]);b.release()
        db_b=Path(desc['local_path'])/'journal.sqlite'
        db_a=a.dir/'journal.sqlite'
        before=fd_keys(w.process.pid)
        snapshot=w.do('open_display_snapshot',session=a.session)['projection']['snapshot']
        staged=fd_keys(w.process.pid)-before
        assert len(staged)==1, staged
        a.write([msg(2,"new WAL frame")])
        ck_old=checkpoint(db_a)
        assert ck_old[0]==1 and ck_old[1]>ck_old[2], ck_old
        assert not (db_b.parent/'.storage-catalog-v1.json').exists(), 'B unexpectedly warm'
        lk=sqlite3.connect(db_b,timeout=1)
        assert lk.execute('PRAGMA locking_mode=EXCLUSIVE').fetchone()[0]=='exclusive'
        lk.execute('BEGIN EXCLUSIVE')
        assert lk.execute('SELECT count(*) FROM journal').fetchone()[0]==1
        ro=sqlite3.connect(f'file:{db_b}?mode=ro',uri=True,timeout=0)
        try:
            try: ro.execute('SELECT count(*) FROM journal')
            except sqlite3.OperationalError as e: assert 'locked' in str(e)
            else: raise AssertionError('second connection was not blocked')
        finally: ro.close()
        lib=ctypes.CDLL(None,use_errno=True)
        fd=lib.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        assert fd>=0 and lib.inotify_add_watch(fd,os.fsencode(db_b),0x20)>=0
        replies=queue.Queue()
        def read():
            while line:=w.process.stdout.readline():
                replies.put((time.monotonic(),json.loads(line)))
        th=threading.Thread(target=read,daemon=True);th.start()
        rb=send(w,mode,session=b.session)
        assert select.select([fd],[],[],2)[0], 'B did not open its journal'
        os.read(fd,65536)
        t=time.monotonic(); ra=send(w,'release_snapshot',snapshot=snapshot)
        try: seen=[replies.get(timeout=.4)]
        except queue.Empty: seen=[]
        ack_before_unlock=bool(seen)
        assert not seen or seen[0][1]['id']==ra, seen
        stage_during=staged<=fd_keys(w.process.pid)
        ck_during=checkpoint(db_a)
        lk.rollback();lk.close();lk=None
        unlocked_at=time.monotonic()
        while len(seen)<2: seen.append(replies.get(timeout=10))
        byid={r['id']:(stamp,r['result']) for stamp,r in seen}
        assert byid[ra][1]=={'result':'done'},byid[ra]
        snap_b=byid[rb][1].get('snapshot') or byid[rb][1]['projection']['snapshot']
        assert snap_b['revision']=={'session_seq':1,'history_revision':1}
        ck_after=checkpoint(db_a)
        assert ck_after==(0,0,0), ck_after
        assert not staged&fd_keys(w.process.pid)
        assert stage_during == (not ack_before_unlock)
        assert ck_during[0] == (not ack_before_unlock)
        assert ack_before_unlock == (mode == 'open_display_snapshot')
        again=send(w,'read_display_records',snapshot=snapshot,after_seq=0,limit=1)
        _, err=replies.get(timeout=4)
        assert err['id']==again and 'expired or unknown' in str(err['error']), err
        w.process.stdin.close();th.join(timeout=4)
        assert w.process.wait(timeout=4)==0
        return dict(mode=mode,ack_before_unlock=ack_before_unlock,stage_present_while_B_locked=stage_during,
                    stage_closed_after_ack=True,checkpoint_before=ck_old,checkpoint_while_B_locked=ck_during,
                    checkpoint_after=ck_after,release_ms=round((byid[ra][0]-t)*1000,3),
                    release_ack_minus_unlock_ms=round((byid[ra][0]-unlocked_at)*1000,3))
    finally:
        if fd>=0: os.close(fd)
        if lk is not None: lk.close()
        w.close()

with tempfile.TemporaryDirectory(prefix='proteus-release-probe-') as temp:
    print(json.dumps(dict(worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),**run(Path(temp))),indent=2))
