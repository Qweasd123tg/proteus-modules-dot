#!/usr/bin/env python3
"""Create two synthetic sessions; verify SQLite empty vs committed WAL ordering."""
import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import ExitStack, closing
from pathlib import Path
from rpc import Client, append, setup, u

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("worker", type=Path)
p.add_argument("--reference-worker", type=Path, help="stock worker used to seed an older v1 index for the fixed reader")
p.add_argument("--behavior", choices=("stock","fixed"), required=True)
a = p.parse_args()
binary=a.worker.resolve()
assert a.reference_worker is None or a.behavior=="fixed"
reference=a.reference_worker.resolve() if a.reference_worker else None
assert reference is None or hashlib.sha256(reference.read_bytes()).digest()!=hashlib.sha256(binary.read_bytes()).digest()
print(f"{a.behavior} SDK worker SHA256={hashlib.sha256(binary.read_bytes()).hexdigest()}",flush=True)

def shadow_stamp(path):
    s=path.stat()
    return s.st_ino,s.st_mtime_ns,s.st_ctime_ns,hashlib.sha256(path.read_bytes()).digest()

def fake_time(path,sec):
    os.utime(path,ns=(sec*1_000_000_000,)*2)

def reader(path):
    con=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)
    try:
        con.execute("BEGIN")
        assert con.execute("select count(*) from journal").fetchone()==(8,)
    except:
        con.close()
        raise
    return con

def fixture(td):
    cfg=td/"config";cfg.mkdir()
    ws=td/"workspace";ws.mkdir()
    lp=dict(config_root=str(cfg),workspace_path=str(ws),audit=False)
    with Client(binary,"sqlite") as seed:
        paths=[setup(seed,cfg,ws,i) for i in range(2)]
    a_dir,b_dir=paths
    journal=[d/"journal.sqlite" for d in paths]
    wal=[d/"journal.sqlite-wal" for d in paths]
    cards=[d/".storage-catalog-v1.json" for d in paths]
    expect_ids=(u(1),u(2))
    def check(c,operation,label,latest,b_hint=None,counts=None):
        resp=c.call(operation,**lp) if operation=="list" else c.call(operation,config_root=str(cfg),workspace_path=str(ws))
        assert resp["result"]==("sessions" if operation=="list" else "candidates")
        rows=resp["sessions"]
        desc=[r["descriptor"] for r in rows] if operation=="list" else rows
        order=[expect_ids.index(out["session"]["session_id"]) for out in desc]
        expected=[latest,1-latest]
        assert order==expected,(label,order,[x["updated_at_ms"] for x in desc])
        if b_hint is not None:
            by_id={expect_ids.index(x["session"]["session_id"]):x["updated_at_ms"] for x in desc}
            assert by_id[0]==b_hint and by_id[1]==20_000_000,(label,by_id,b_hint)
        if counts is not None:
            assert [r["message_count"] for r in rows]==counts
        return "AB" if order==[0,1] else "BA"
    assert not any(x.exists() for x in wal), "expected writer shutdown to checkpoint the initial sessions"
    for path,sec in zip(journal,[10_000,20_000]):
        fake_time(path,sec)
    with Client(binary,"sqlite") as resident:
        order=check(resident,"list_candidates","missing WALs",1,10_000_000)
        print(f"{a.behavior} missing WAL: order={order}",flush=True)
        with ExitStack() as held:
            module_reader=held.enter_context(Client(binary,"sqlite"))
            s=module_reader.call("open",path=str(a_dir))["descriptor"]["session"]
            pinned=module_reader.call("open_snapshot",session=s)["snapshot"]
            assert pinned["revision"]["history_revision"]==8
            assert wal[0].is_file() and wal[0].stat().st_size==0
            read_only_mtime=wal[0].stat().st_mtime_ns
            r0=held.enter_context(closing(reader(journal[0])))
            held.enter_context(closing(reader(journal[1])))
            assert all(path.is_file() and path.stat().st_size==0 for path in wal)
            assert read_only_mtime>20_000*1_000_000_000
            # B is not the newly opened session in the observation. Age its
            # empty file so that it cannot conceivably outrank A by wall time.
            fake_time(wal[1],9_000)
            expected_a=(a.behavior=="stock")
            ts_when_empty=read_only_mtime//1_000_000 if expected_a else 10_000_000
            order=check(resident,"list_candidates","genuine empty WAL",0 if expected_a else 1,ts_when_empty)
            print(f"{a.behavior} held native OpenSnapshot created zero-byte WAL: order={order}",flush=True)
            for card in cards:
                card.unlink(missing_ok=True)
            with Client(binary,"sqlite") as fresh:
                cold=check(fresh,"list","cold replay",0 if expected_a else 1,ts_when_empty,counts=[8,8])
            print(f"{a.behavior} zero-byte WAL and no sidecars: strict cold List={cold}",flush=True)
            # Start cache tests with either absence or an old, equivalent zero.
            # No journal data or session metadata is changed in the next phase.
            fake_time(wal[0],9_000)
            check(resident,"list","seed memory and disk",1,10_000_000,counts=[8,8])
            before=tuple(shadow_stamp(path) for path in cards)
            os.utime(wal[0],ns=(read_only_mtime,read_only_mtime))
            assert wal[0].stat().st_size==0
            ordering=0 if expected_a else 1
            warm=check(resident,"list","warm hit",ordering,ts_when_empty,counts=[8,8])
            assert before==tuple(shadow_stamp(path) for path in cards)
            with Client(binary,"sqlite") as fresh:
                disk=check(fresh,"list","fresh disk hit",ordering,ts_when_empty,counts=[8,8])
            assert before==tuple(shadow_stamp(path) for path in cards)
            print(f"{a.behavior} zero-byte WAL only changed mtime: memory={warm} disk={disk}; sidecars unchanged",flush=True)
            if reference is not None:
                # Old workers may have persisted the placeholder's newer
                # descriptor timestamp. New loader checks its existing checksum
                # then refreshes the descriptor without rewriting those bytes.
                for card in cards:
                    card.unlink()
                with Client(reference,"sqlite") as old:
                    check(old,"list","stock-seeded sidecars",0,read_only_mtime//1_000_000,counts=[8,8])
                cached=json.loads(cards[0].read_bytes())
                assert cached['data']['summary']['descriptor']['updated_at_ms']==read_only_mtime//1_000_000
                old_stamps=tuple(shadow_stamp(path) for path in cards)
                with Client(binary,"sqlite") as fresh:
                    newer=check(fresh,"list","compatible old worker sidecar",1,10_000_000,counts=[8,8])
                assert old_stamps==tuple(shadow_stamp(path) for path in cards)
                print(f"{a.behavior} original v1 sidecar with stale recent descriptor: disk={newer}; old bytes and stamps preserved",flush=True)
            with Client(binary,"sqlite") as writer:
                s=writer.call("open",path=str(a_dir))["descriptor"]["session"]
                wr=writer.call("acquire_writer",session=s)
                rev=append(writer,wr["lease"],wr["revision"],0,8,"committed while reader is held")
                assert rev["history_revision"]==9
                size=wal[0].stat().st_size
                assert size>0
                assert r0.execute("select count(*) from journal").fetchone()==(8,), "old reader lost its snapshot"
                page=module_reader.call("read_records",snapshot=pinned,after_seq=0,limit=32)["page"]
                assert page["snapshot"]==pinned and page["next_after_seq"] is None
                assert [r["session_seq"] for r in page["records"]]==list(range(1,9))
                timestamp=wal[0].stat().st_mtime_ns//1_000_000
                assert timestamp>20_000_000
                order=check(resident,"list_candidates","nonempty committed WAL",0,timestamp)
                check(resident,"list","ordinary strict list with committed WAL",0,timestamp,counts=[9,8])
                with Client(binary,"sqlite") as fresh:
                    check(fresh,"list","fresh strict list with committed WAL",0,timestamp,counts=[9,8])
                print(f"{a.behavior} writer committed with WAL={size} bytes: order={order}, pinned reader 8, new List 9",flush=True)
                writer.call("release_writer",lease=wr["lease"])
            module_reader.call("release_snapshot",snapshot=pinned)

with tempfile.TemporaryDirectory(prefix="r48-synthetic-") as d:
    fixture(Path(d))
