#!/usr/bin/env python3
"""Count exact SDK WriteCache allocations; one scratch build with two path modes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
from collections import Counter

from cache_client import Client, u


def timeout(_sig, _frame):
    raise TimeoutError("local SDK worker did not respond")


def norm(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(x): return hashlib.sha256(x).hexdigest()


def fixture(binary, cpu, backend, root):
    workspace=root/"project"
    workspace.mkdir()
    with Client(binary,cpu,backend) as c:
        d=c.call("create",config_root=str(root/"config"),workspace_path=str(workspace),session_id=u(1),
                 parent_session_id=None)["descriptor"]
        session=d["session"]
        w=c.call("acquire_writer",session=session)
        message=dict(id=u(20),role="User",phase=None,parts=[dict(part_id=u(21),provenance="user",scope="conversation",
            payload={"Text":{"text":"normal disposable display page"}})],name=None,tool_call_id=None,metadata={})
        entry=dict(kind="history_mutated",payload=dict(previous_revision=0,new_revision=1,mutation="append",
                   messages=[message],compaction=None,tool_results=[]))
        c.call("commit",commit=dict(lease=w["lease"],operation_id=u(22),expected=w["revision"],timestamp_ms=100,
                   attribution=dict(execution_id=None,thread_id=u(10),turn_id=None),entry=entry))
        c.call("release_writer",lease=w["lease"])
    return d


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("worker",type=Path)
    ap.add_argument("--stock-original",type=Path)
    ap.add_argument("--pairs",type=int,default=3)
    a=ap.parse_args()
    assert a.pairs>0
    a.worker=a.worker.resolve(strict=True)
    if a.stock_original:
        a.stock_original=a.stock_original.resolve(strict=True)
    signal.signal(signal.SIGALRM,timeout)
    cpu=min(os.sched_getaffinity(0))
    for backend in ("jsonl","sqlite"):
        with tempfile.TemporaryDirectory() as tmp:
            d=fixture(a.worker,cpu,backend,Path(tmp))
            session=d["session"]; directory=Path(d["local_path"])
            source_oracle=None
            response_and_blob=None
            measured={}
            for pair in range(a.pairs+1):
                for stock in ((True,False) if pair%2 else (False,True)):
                    for path in directory.glob(".storage-cache-*.json"):
                        assert path.is_file() and not path.is_symlink()
                        path.unlink()
                    with Client(a.worker,cpu,backend,stock=stock) as c:
                        snapshot=c.call("open_snapshot",session=session)["snapshot"]
                        stable=dict(snapshot); del stable["snapshot_id"]
                        if source_oracle is None: source_oracle=stable
                        assert stable==source_oracle
                        rows=[]; allocations=[]
                        for seq in range(320):
                            key=f"derived-page-{seq:03d}"
                            value={"offset":seq*50, "text":"Синтетическая страница. "*32, "version":1}
                            res=c.call("write_cache",session=session,key=key,source=snapshot,value=value)
                            assert res=={"result":"cache_written","etag":digest(norm(value))}
                            allocations.append(c.allocation())
                            path=directory/f".storage-cache-{digest(key.encode())}.json"
                            file=json.loads(path.read_bytes())
                            assert file==dict(source=snapshot,value=value)
                            file["source"]=stable
                            if seq in (0,127,319):
                                meta=c.call("read_cache",session=session,key=key,source=snapshot)
                                assert meta=={"result":"metadata","document":{"etag":res["etag"],"value":value}}
                            rows.append([res,norm(file)])
                        assert len(list(directory.glob(".storage-cache-*.json")))==320
                        if response_and_blob is None: response_and_blob=rows
                        assert response_and_blob==rows
                        measured[pair,stock]=allocations
            diffs=Counter((b[0]-x[0],b[1]-x[1]) for p in range(1,a.pairs+1)
                          for b,x in zip(measured[p,True],measured[p,False]))
            assert all(calls>0 and volume>0 for calls,volume in diffs)
            if a.stock_original:
                # Read the candidate's normal files with the original binary.
                with Client(a.stock_original,cpu,backend) as stock:
                    source=stock.call("open_snapshot",session=session)["snapshot"]
                    for seq in (0,127,319):
                        key=f"derived-page-{seq:03d}"
                        ref=stock.call("read_cache",session=session,key=key,source=source)["document"]
                        assert ref["etag"]==response_and_blob[seq][0]["etag"]
            print(json.dumps(dict(backend=backend,paired_runs=a.pairs,matched_records=320,
                                  alloc_difference_by_write=[{"calls":c,"requested_bytes":b,"writes":n}
                                                             for (c,b),n in sorted(diffs.items())],
                                  exact_response_path_and_cache_content=True,
                                  original_workspace_worker_readback=bool(a.stock_original))))
if __name__=="__main__": main()
