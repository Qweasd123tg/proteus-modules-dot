#!/usr/bin/env python3
"""Fresh genuine workers on one valid on-disk catalog. No user data or real config."""
import argparse
import hashlib
import sqlite3
import tempfile
from contextlib import ExitStack
from pathlib import Path
from rpc import Client, setup

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("stock", type=Path)
p.add_argument("candidate", type=Path)
a = p.parse_args()
bins = tuple(p.resolve() for p in (a.stock, a.candidate))
assert bins[0] != bins[1] and all(p.is_file() for p in bins)

def stamp(path):
    st = path.stat()
    return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, hashlib.sha256(path.read_bytes()).digest())

for backend in ("jsonl", "sqlite"):
    with tempfile.TemporaryDirectory(prefix="r46-sdk-") as temp, ExitStack() as stack:
        td = Path(temp)
        cfg = td / "config"
        ws = td / "workspace"
        cfg.mkdir()
        ws.mkdir()
        lp = dict(config_root=str(cfg), workspace_path=str(ws), audit=False)
        with Client(bins[0], backend) as seed:
            paths = [setup(seed,cfg,ws,i) for i in range(10)]
        for d in paths:
            b = d / "blobs"
            b.mkdir(exist_ok=True)
            for i in range(48):
                (b / f"inventory-{i:04}.fixture").touch()
            if backend == "sqlite":
                con = sqlite3.connect((d / "journal.sqlite").as_uri()+"?mode=ro",uri=True)
                stack.callback(con.close)
                con.execute("select count(*) from journal").fetchall()
        with Client(bins[0], backend) as seed:
            expected = seed.call("list", **lp)
        cards = [d / ".storage-catalog-v1.json" for d in paths]
        before = [stamp(path) for path in cards]
        session = expected["sessions"][0]["descriptor"]["session"]
        assert len(expected["sessions"]) == 10
        for pair in range(3):
            actual = []
            for binary in bins[::(-1 if pair%2 else 1)]:
                # Dedicated fresh processes so neither RPC can use memory cache.
                with Client(binary,backend) as worker:
                    assert worker.call("list", **lp) == expected
                assert before == [stamp(path) for path in cards], "List rewrote valid cache"
                with Client(binary,backend) as worker:
                    snapshot = worker.call("open_snapshot", session=session)["snapshot"]
                    worker.call("release_snapshot", snapshot=snapshot)
                assert before == [stamp(path) for path in cards], "OpenSnapshot rewrote valid cache"
                snapshot.pop("snapshot_id") # intentionally random lifetime handle
                actual.append(snapshot)
            assert actual[0] == actual[1], (backend,actual)
        print(f"{backend}: 3 exact paired 10-row List and direct OpenSnapshot, valid sidecars unchanged")
