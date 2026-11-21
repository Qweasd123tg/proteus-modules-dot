#!/usr/bin/env python3
"""Compare same-generation cold List bytes and valid-disk hits of two real SDK workers."""
import argparse
import hashlib
import json
import resource
import sqlite3
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from rpc import Client, setup

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("stock", type=Path)
p.add_argument("candidate", type=Path)
p.add_argument("--pairs", default=7, type=int)
a = p.parse_args()
bins = {name:getattr(a,name).resolve() for name in ("stock","candidate")}
assert 1<=a.pairs<=11
assert hashlib.sha256(bins['stock'].read_bytes()).digest()!=hashlib.sha256(bins['candidate'].read_bytes()).digest()

def child_cpu_ns():
    usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    return round((usage.ru_utime+usage.ru_stime)*1_000_000_000)

def content(cards):
    return tuple(p.read_bytes() for p in cards)

def file_stamps(cards):
    return tuple((st.st_ino,st.st_mtime_ns,st.st_ctime_ns) for st in (p.stat() for p in cards))

def seed_inventory(paths):
    for path in paths:
        b=path/"blobs"
        b.mkdir(exist_ok=True)
        for bucket in range(8):
            (b/f"bucket-{bucket}").mkdir()
        for i in range(492):
            (b/f"bucket-{i%8}"/f"fixture-{i:04}-{'x'*(i%11)}.bin").touch(exist_ok=False)

for backend in ("jsonl", "sqlite"):
    with tempfile.TemporaryDirectory(prefix="r47-sdk-") as root, ExitStack() as stack:
        td=Path(root)
        cfg,ws=td/"config",td/"workspace";cfg.mkdir();ws.mkdir()
        args=dict(config_root=str(cfg),workspace_path=str(ws),audit=False)
        with Client(bins["stock"],backend) as c:
            paths=[setup(c,cfg,ws,i) for i in range(10)]
        seed_inventory(paths)
        cards=[d/".storage-catalog-v1.json" for d in paths]
        if backend=="sqlite":
            for d in paths:
                con=sqlite3.connect((d/"journal.sqlite").as_uri()+"?mode=ro",uri=True)
                stack.callback(con.close)
                con.execute("select count(*) from journal").fetchall()
        def call(name):
            cpu0=child_cpu_ns()
            with Client(bins[name],backend) as c:
                t0=time.perf_counter_ns()
                rows=c.call("list",**args)
                ns=time.perf_counter_ns()-t0
            cpu=child_cpu_ns()-cpu0
            assert rows["result"]=="sessions" and len(rows["sessions"])==10
            out=content(cards)
            assert all(len(json.loads(b)["data"]["blobs"]) >= 500 for b in out)
            return rows,out,ns,cpu
        for trial in range(a.pairs):
            parity=None
            for name in (("stock","candidate") if trial%2==0 else ("candidate","stock")):
                for card in cards:
                    card.unlink(missing_ok=True)
                rows,raw,cold_ns,cold_cpu=call(name)
                if parity is None:
                    parity=(rows,raw)
                else:
                    assert parity==(rows,raw)
                before=file_stamps(cards)
                warm,wraw,warm_ns,disk_cpu=call(name)
                assert before==file_stamps(cards) and (rows,raw)==(warm,wraw)
                print(json.dumps(dict(backend=backend,trial=trial,variant=name,
                    cold_ns=cold_ns,disk_ns=warm_ns,cold_worker_cpu_ns=cold_cpu,disk_worker_cpu_ns=disk_cpu,sidecar_bytes=sum(map(len,raw))),separators=(',',':')))
        # Both implementations must retire the same stale generation and emit
        # identical replacement bytes after an ordinary nested mutation.
        stale=cards[0].read_bytes()
        with (paths[0]/"blobs/bucket-0/added-fixture").open("xb"):
            pass
        expect,first,_,_=call("stock")
        assert stale!=first[0]
        cards[0].write_bytes(stale)
        got,second,_,_=call("candidate")
        assert expect==got and first==second
        print(json.dumps(dict(backend=backend,stale_repair_identical=True)))
