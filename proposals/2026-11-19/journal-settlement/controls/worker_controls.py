#!/usr/bin/env python3
"""Regression controls for an unmodified or candidate Proteus storage worker.

Writes synthetic journals and disposable cache files ONLY in TemporaryDirectory.
Usage: python3 worker_controls.py /absolute/path/to/proteus-session-storage-module
"""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


def uid(i): return str(uuid.UUID(int=i))


class Worker:
    def __init__(self, binary, kind):
        self.seq = 0
        self.kind = kind
        self.process = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.frame("initialize", {"protocol_version": "v3", "component_id": "controls",
            "exports": [{"slot": "session_storage", "module_id": kind, "contract_version": "v1",
                         "composition": "select_one", "module_config": {}, "host_features": []}]})

    def frame(self, method, args, fail=False):
        ident = f"h:1:{self.seq}"
        self.seq += 1
        self.process.stdin.write(json.dumps(dict(jsonrpc="2.0", id=ident, method=method,
            params=args), separators=(",", ":")).encode() + b"\n")
        self.process.stdin.flush()
        r = json.loads(self.process.stdout.readline())
        assert r["id"] == ident
        if fail:
            assert "error" in r, f"{method}: expected failure but got success"
            return str(r["error"])
        assert "error" not in r, r.get("error")
        return r["result"]

    def do(self, operation, fail=False, **params):
        return self.frame("execute", {"export": {"slot": "session_storage", "module_id": self.kind},
            "lineage": {"root_invocation_id": f"h:1:{self.seq}", "parent_invocation_id": None, "depth": 0},
            "params": {"operation": operation, **params}}, fail)

    def close(self):
        if not self.process.stdin.closed:
            self.process.stdin.close()
            try: self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=4)
            self.process.stdout.close()


def msg(i, text):
    return dict(id=uid(1000+i), role="User", phase=None, name=None, tool_call_id=None, metadata={},
        parts=[dict(part_id=uid(2000+i), provenance="user", scope="conversation", payload={"Text": {"text": text}})])


class Fixture:
    def __init__(self, binary, kind, root):
        self.binary = binary
        self.kind = kind
        self.w = Worker(binary, kind)
        cwd = root/"work"
        cwd.mkdir()
        d = self.w.do("create", config_root=str(root/"config"), workspace_path=str(cwd),
                       session_id=uid(7), parent_session_id=None)["descriptor"]
        self.session = d["session"]
        self.dir = Path(d["local_path"])
        assert self.dir.is_relative_to(root), "temporary fixture path"
        self.acquire()

    def acquire(self):
        result = self.w.do("acquire_writer", session=self.session)
        self.lease = result["lease"]
        self.rev = result["revision"]

    def release(self): self.w.do("release_writer", lease=self.lease)

    def write(self, messages, mutation="append", compaction=None):
        i = self.rev['session_seq'] + 1
        before = self.rev["history_revision"]
        commit = dict(lease=self.lease, operation_id=uid(100+i), expected=self.rev,
            timestamp_ms=1234+i, attribution=dict(execution_id=None, thread_id=uid(9800), turn_id=None),
            entry=dict(kind="history_mutated", payload=dict(mutation=mutation, previous_revision=before,
                new_revision=before+1, messages=messages, compaction=compaction, tool_results=[])))
        ack = self.w.do("commit", commit=commit)["ack"]
        self.rev = ack["revision"]
        return commit, ack

    def snap(self): return self.w.do("open_snapshot", session=self.session)["snapshot"]

    def hist(self, snap, **point): return self.w.do("read_conversation", snapshot=snap,
        point=point or {"kind":"current"})["conversation"]["messages"]

    def cmp(self, snap, pref): return self.w.do("compare_snapshots", snapshot=snap, prefix=pref)["matches"]


@contextmanager
def fixture(binary, kind):
    with tempfile.TemporaryDirectory() as d:
        f = Fixture(binary, kind, Path(d))
        try: yield f
        finally: f.w.close()


def exact_prefix(f):
    a, b = msg(1, "old"), msg(2, "new")
    f.write([a])
    old = f.snap()
    f.write([b])
    latest = f.snap()
    assert f.hist(old) == [a] and f.hist(latest) == [a,b]
    f.w.do("release_snapshot", snapshot=old)
    assert f.cmp(latest, old)
    assert not f.cmp(latest, dict(old, revision=dict(old["revision"],history_revision=0)))
    assert not f.cmp(latest, dict(old, content_sha256="0"*64))
    assert "expired" in f.w.do("read_records", fail=True, snapshot=old, after_seq=0, limit=2).lower()


def writer_restart(f):
    peer = Worker(f.binary, f.kind)
    try:
        assert peer.do("acquire_writer", fail=True, session=f.session)
        stale_lease = f.lease
        a, b = msg(1, "first lease"), msg(2, "later writer")
        op1, ack1 = f.write([a])
        old = f.snap()
        f.release()
        f.w.close()
        f.w, peer = peer, f.w
        f.acquire()
        assert f.rev == ack1["revision"]
        assert "expired" in f.w.do("read_records", fail=True, snapshot=old, after_seq=0, limit=2).lower()
        assert f.w.do("commit",fail=True,commit=dict(op1, lease=stale_lease))
        assert f.w.do("commit",commit=dict(op1, lease=f.lease))["ack"] == ack1
        f.write([b])
        latest = f.snap()
        assert f.cmp(latest, old) and f.hist(latest) == [a,b]
        assert f.w.do("write_cache", session=f.session, key="old-head", source=old,
                      value={"n":1})["etag"] is None
    finally:
        peer.close()


def external_reader(f):
    x, y, z = msg(1,"reader-page-A"), msg(2,"reader-page-B"), msg(3,"later writer")
    _, a = f.write([x]); _, b = f.write([y])
    reader = Worker(f.binary, f.kind)
    try:
        old = reader.do("open_snapshot",session=f.session)["snapshot"]
        page = reader.do("read_records",snapshot=old,after_seq=0,limit=1)["page"]
        assert page["records"]==[a["record"]] and page["next_after_seq"]==1
        f.write([z])
        page = reader.do("read_records",snapshot=old,after_seq=1,limit=64)["page"]
        assert page["records"]==[b["record"]] and page["next_after_seq"] is None
        latest = reader.do("open_snapshot",session=f.session)["snapshot"]
        assert reader.do("compare_snapshots",snapshot=latest,prefix=old)["matches"]
        assert reader.do("read_conversation",snapshot=latest,point={"kind":"current"})["conversation"]["messages"]==[x,y,z]
    finally:
        reader.close()


def compaction(f):
    a, summary, after = msg(1, "before compact"), msg(2, "replaced by summary"), msg(3, "reset")
    f.write([a])
    old = f.snap()
    report = dict(changed=True, user_message_replacements=[], reason=None, input_messages=1,
        output_messages=1, original_token_estimate=None, output_token_estimate=None, trigger_tokens=None,
        summary_source=None, skipped_reason=None, summary=None, metadata=None)
    f.write([summary], mutation="replace", compaction=report)
    middle = f.snap()
    assert f.cmp(middle, old), "physical append and logical append are distinct"
    assert f.hist(middle)==[summary] and f.hist(middle, kind="before_replacement",
        part_id=summary["parts"][0]["part_id"]) == [a]
    f.write([after], mutation="replace")
    latest = f.snap()
    assert f.hist(latest)==[after] and f.hist(old)==[a]
    assert "unavailable" in f.w.do("read_conversation", fail=True, snapshot=latest,
        point={"kind":"revision","history_revision":1}).lower()


def cache_loss(f):
    a = msg(1, "canonical")
    f.write([a]); old = f.snap()
    key = "r7-disposable-cache"
    value = {"read_only_preview":"not canonical"}
    assert f.w.do("write_cache", session=f.session, key=key, source=old, value=value)["etag"]
    assert f.w.do("read_cache", session=f.session, key=key, source=old)["document"]["value"] == value
    disk = f.dir / (".storage-cache-"+hashlib.sha256(key.encode()).hexdigest()+".json")
    disk.write_bytes(b"{")
    assert f.w.do("read_cache", session=f.session, key=key, source=old)["document"] is None
    assert f.hist(old)==[a]
    disk.unlink()
    assert f.w.do("read_cache", session=f.session, key=key, source=old)["document"] is None
    assert f.hist(f.snap())==[a]


def blob(f):
    a = msg(1, "p"*300000); b=msg(2,"tail")
    f.write([a]); old = f.snap()
    f.write([b]); latest = f.snap()
    w = f.w
    assert f.cmp(latest, old)
    assert f.hist(latest)==[a,b]
    warm = f.snap()
    assert warm["content_sha256"]==latest["content_sha256"]
    path, = (f.dir/"blobs").glob("*.json")
    journal = f.dir/"journal.jsonl"
    before = journal.stat()
    content = path.read_bytes()
    # Use deterministic bit-preserving-length change in a known synthetic payload.
    assert b"pppp" in content
    path.write_bytes(content.replace(b"pppp", b"qqqq", 1))
    assert journal.stat().st_mtime_ns==before.st_mtime_ns and journal.stat().st_size==before.st_size
    warm2=f.snap()
    assert warm2["content_sha256"]==latest["content_sha256"] and warm2["revision"]==latest["revision"]
    for pinned, prefix in [(warm2, old), (latest, old), (latest, latest)]:
        # Also exercise the already-verified capture and both possible saved cuts.
        assert "blob hash mismatch" in w.do("compare_snapshots",fail=True,snapshot=pinned,prefix=prefix)
    assert "blob hash mismatch" in w.do("read_records", fail=True, snapshot=warm, after_seq=1, limit=1)
    # Restore then remove temporarily. The hash/revision still cannot establish availability.
    path.unlink()
    assert f.w.do("read_conversation", fail=True, snapshot=warm2, point={"kind":"current"})
    path.write_bytes(content)
    assert f.cmp(warm2, old) and f.hist(warm2)==[a,b]


def replacement(f):
    a=msg(1,"branch-A1"); new=msg(1,"branch-B1")
    f.write([a]); old=f.snap(); f.release()
    journal=f.dir/"journal.jsonl"
    # Atomic ordinary replacement, all identities/revisions and physical length remain identical.
    source=journal.read_bytes()
    changed=source.replace(b"branch-A1",b"branch-B1")
    assert len(changed)==len(source) and changed!=source
    staging=f.dir/"replacement.tmp"; staging.write_bytes(changed)
    os.replace(staging,journal)
    latest=f.snap()
    assert old["revision"]==latest["revision"] and old["content_sha256"]!=latest["content_sha256"]
    assert not f.cmp(latest,old) and f.hist(old)==[a] and f.hist(latest)==[new]


def in_place_change(f):
    a,b=msg(1,"inline-abc"),msg(2,"retained-tail")
    f.write([a]); old=f.snap()
    f.write([b]); latest=f.snap()
    assert f.cmp(latest,old)
    journal=f.dir/"journal.jsonl"
    content=journal.read_bytes(); before=journal.stat()
    altered=content.replace(b"inline-abc",b"inline-xyz")
    assert content!=altered and len(content)==len(altered)
    journal.write_bytes(altered)
    os.utime(journal, ns=(before.st_atime_ns, before.st_mtime_ns))
    # Same inode/length/mtime and caller-supplied revision are insufficient.
    # Verify the old pinned object; a newly-opened descriptor may be provisional.
    assert f.w.do("compare_snapshots",fail=True,snapshot=latest,prefix=old)
    assert f.w.do("read_records",fail=True,snapshot=latest,after_seq=1,limit=1)
    journal.write_bytes(content)
    assert f.cmp(latest,old) and f.hist(latest)==[a,b]


def same_service_clients(f):
    second=f.w.do("acquire_writer",session=f.session)
    assert second["lease"]["generation"]==f.lease["generation"]
    assert second["lease"]["token"]!=f.lease["token"]
    a=msg(1,"shared writer")
    op,ack=f.write([a])
    assert f.w.do("commit",commit=dict(op,lease=second["lease"]))["ack"]==ack
    assert "revision conflict" in f.w.do("commit", fail=True,
        commit=dict(op,lease=second["lease"],operation_id=uid(909))).lower()
    f.release()
    f.lease=second["lease"]
    b=msg(2,"survives release")
    f.write([b]); snap=f.snap()
    assert f.hist(snap)==[a,b]


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("worker", type=Path)
    args=parser.parse_args()
    binary=str(args.worker.resolve(strict=True)); cases=0
    print("worker.sha256",hashlib.sha256(Path(binary).read_bytes()).hexdigest(),flush=True)
    for kind in ("jsonl","sqlite"):
        tests=[exact_prefix,writer_restart,same_service_clients,external_reader,compaction,cache_loss] + ([replacement,in_place_change,blob] if kind=="jsonl" else [])
        for test in tests:
            with fixture(binary,kind) as f: test(f)
            cases+=1
            print("PASS",kind,test.__name__,flush=True)
    print(f"{cases} scenario/backend pairs passed")
if __name__ == "__main__": main()
