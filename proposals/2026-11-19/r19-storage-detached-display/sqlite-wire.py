"""Exercise two concurrent SDK invokes in one actual SQLite module process.
Run: python3 sqlite-wire.py /path/to/module [directory-containing-rpc.py]
Uses synthetic tempdirs only. No patched worker or injected server hooks.
"""
import ctypes, hashlib, json, os, queue, select, sqlite3, sys, tempfile, threading, time
from pathlib import Path
if len(sys.argv)>2: sys.path.insert(0, str(Path(sys.argv[2]).resolve()))
from rpc import Fixture, msg, uid
binary = Path(sys.argv[1]).resolve(strict=True)

def start(w, operation, **kwargs):
    ident = f"h:1:{w.seq}"
    w.seq += 1
    params = dict(export=dict(slot="session_storage",module_id="sqlite"),
        lineage=dict(root_invocation_id=ident,parent_invocation_id=None,depth=0),
        params=dict(operation=operation, **kwargs))
    w.process.stdin.write(json.dumps(dict(jsonrpc="2.0",id=ident,method="execute",params=params)).encode()+b'\n')
    w.process.stdin.flush()
    return ident

def one(root):
    a = Fixture(str(binary), 'sqlite', root)
    w = a.w
    lock = None
    fd = -1
    try:
        commit,_ = a.write([msg(1, "active")])
        b = Fixture.__new__(Fixture); b.w = w
        d = w.do("create",config_root=str(root/"config"),workspace_path=str(root/"work"),
            session_id=uid(8),parent_session_id=None)["descriptor"]
        b.session = d["session"]; b.acquire()
        b.write([msg(2, "cold")]); b.release()
        db = Path(d["local_path"])/"journal.sqlite"
        lock = sqlite3.connect(db,timeout=1)
        assert lock.execute("PRAGMA locking_mode=EXCLUSIVE").fetchone()[0]=="exclusive"
        lock.execute("BEGIN EXCLUSIVE")
        assert lock.execute("SELECT count(*) FROM journal").fetchone()[0]==1
        # Confirm the setup really blocks a second reader, before arming inotify.
        check = sqlite3.connect(f"file:{db}?mode=ro",uri=True,timeout=0)
        try:
            try: check.execute("SELECT count(*) FROM journal").fetchone()
            except sqlite3.OperationalError as e: assert 'locked' in str(e)
            else: raise AssertionError("reader not blocked")
        finally: check.close()
        lib = ctypes.CDLL(None,use_errno=True)
        fd = lib.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        assert fd >= 0 and lib.inotify_add_watch(fd, os.fsencode(db), 0x20) >= 0
        responses = queue.Queue()
        def read():
            while line:=w.process.stdout.readline(): responses.put(json.loads(line))
        th = threading.Thread(target=read,daemon=True); th.start()
        read_id = start(w, "open_display_snapshot", session=b.session)
        assert select.select([fd],[],[],2)[0], "worker did not open B"
        os.read(fd,65536)
        commit.update(operation_id=uid(102),expected=a.rev,timestamp_ms=1236)
        commit["entry"]["payload"].update(previous_revision=1,new_revision=2,messages=[msg(3,"while B locked")])
        sent=time.monotonic()
        write_id = start(w,"commit",commit=commit)
        items = []
        try: items.append(responses.get(timeout=1))
        except queue.Empty: pass
        assert not items or items[0]["id"]==write_id, "B replied before its held external lock was released"
        before_unlock = bool(items)
        ack_ms = (time.monotonic()-sent)*1000 if before_unlock else None
        lock.rollback(); lock.close(); lock=None
        while len(items)<2: items.append(responses.get(timeout=8))
        byid={r["id"]:r for r in items}
        ack=byid[write_id]["result"]["ack"]
        assert ack["revision"]=={"session_seq":2,"history_revision":2} and ack["operation_id"]==uid(102)
        assert ack["record"]["entry"]["payload"]["messages"]==[msg(3,"while B locked")]
        projection=byid[read_id]["result"]["projection"]
        assert projection["snapshot"]["revision"]=={"session_seq":1,"history_revision":1}
        assert projection["state"]["conversation"]["messages"]==[msg(2,"cold")]
        w.process.stdin.close(); th.join(timeout=4)
        assert w.process.wait(timeout=4)==0
        return dict(worker_pid=w.process.pid,ack_before_B_unlock=before_unlock,
            ack_ms_after_A_dispatch_if_before_unlock=round(ack_ms,3) if ack_ms is not None else None,
            durable_revision=ack["revision"],B_exact_state=True, external_lock_confirmed=True, ack_deadline_ms=1000)
    finally:
        if fd>=0: os.close(fd)
        if lock is not None: lock.close()
        w.close()

with tempfile.TemporaryDirectory(prefix="r19-sqlite-wire-") as tmp:
    r=one(Path(tmp))
print(json.dumps(dict(worker_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), **r),indent=2))
