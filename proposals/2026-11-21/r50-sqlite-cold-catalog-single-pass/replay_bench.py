#!/usr/bin/env python3
"""Compare two SDK workers using only healthy, synthetic SQLite sessions (Linux)."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import signal
import statistics
import subprocess
import tempfile
import time
import uuid
from contextlib import closing
from hashlib import sha256


def u(i):
    return str(uuid.UUID(int=i))


class Client:
    def __init__(self, binary, cpu):
        self.child = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        os.sched_setaffinity(self.child.pid, {cpu})
        self.seq = -1
        self.export = dict(slot="session_storage", module_id="sqlite")
        self.rpc("initialize", dict(protocol_version="v3", component_id="sqlite-replay-bench",
            exports=[dict(**self.export, contract_version="v2", composition="select_one",
                          module_config={}, host_features=[])]))

    def rpc(self, method, params):
        self.seq += 1
        ident = f"h:1:{self.seq}"
        request = dict(jsonrpc="2.0", id=ident, method=method, params=params)
        self.child.stdin.write(json.dumps(request, separators=(",", ":")).encode()+b"\n")
        self.child.stdin.flush()
        signal.alarm(45)
        try:
            reply = json.loads(self.child.stdout.readline())
        finally:
            signal.alarm(0)
        assert reply["id"] == ident and "result" in reply, reply
        return reply["result"]

    def call(self, operation, **params):
        return self.rpc("execute", dict(export=self.export, params=dict(operation=operation, **params),
                   lineage=dict(root_invocation_id=f"h:1:{self.seq+1}",
                                parent_invocation_id=None, depth=0)))

    def cpu(self):
        stat = Path(f"/proc/{self.child.pid}/stat").read_text().rpartition(") ")[-1].split()
        return int(stat[11])+int(stat[12])

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.child.stdin.close()
        try:
            self.child.wait(10)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.wait()
        self.child.stdout.close()
        assert self.child.returncode == 0, self.child.returncode


def fixture(binary, cpu, root, count, size):
    workspace = root/"workspace"
    workspace.mkdir()
    listing = dict(config_root=str(root/"config"), workspace_path=str(workspace))
    with Client(binary, cpu) as c:
        descriptor = c.call("create", **listing, session_id=u(1), parent_session_id=None)["descriptor"]
        session = descriptor["session"]
        writer = c.call("acquire_writer", session=session)
        lease = writer["lease"]
        revision = writer["revision"]
        for n in range(count):
            msg = dict(id=u(10000+3*n), role="User", phase=None,
                parts=[dict(part_id=u(10001+3*n), provenance="user", scope="conversation",
                            payload={"Text": {"text": "x"*size}})],
                name=None, tool_call_id=None, metadata={})
            entry = dict(kind="history_mutated", payload=dict(previous_revision=n, new_revision=n+1,
                mutation="append", messages=[msg], compaction=None, tool_results=[]))
            commit = dict(lease=lease, operation_id=u(10002+3*n), expected=revision, timestamp_ms=n,
                          attribution=dict(execution_id=None, thread_id=u(2), turn_id=None), entry=entry)
            revision = c.call("commit", commit=commit)["ack"]["revision"]
        c.call("release_writer", lease=lease)
    return listing, descriptor


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--pairs", default=9, type=int)
    p.add_argument("--cpu", default=min(os.sched_getaffinity(0)), type=int)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    assert args.pairs >= 1
    bins = {"stock": args.stock.resolve(strict=True), "candidate": args.candidate.resolve(strict=True)}
    print("CPU:", args.cpu, "ticks/second:", os.sysconf("SC_CLK_TCK"), flush=True)
    def timeout(_sig, _frame):
        raise TimeoutError("SDK worker did not respond")
    signal.signal(signal.SIGALRM, timeout)
    hashes = {}
    for label, binary in bins.items():
        with binary.open("rb") as f:
            hashes[label] = hashlib.file_digest(f, "sha256").hexdigest()
            print(label, hashes[label], flush=True)
    assert hashes["stock"] != hashes["candidate"], "expected binaries from distinct source builds"

    with args.output.open("w", newline="") as out:
        fields = ("case", "pair", "label", "audit", "rows", "payload_bytes", "wall_ns", "cpu_ticks")
        csv_out = csv.writer(out, lineterminator="\n")
        csv_out.writerow(fields)
        for case, rows, body in (("empty", 0, 0), ("small", 64, 512),
                                 ("many", 1536, 512), ("large", 128, 262144)):
            with tempfile.TemporaryDirectory() as tmp:
                listing, desc = fixture(bins["stock"], args.cpu, Path(tmp), rows, body)
                journal = Path(desc["local_path"])/"journal.sqlite"
                index = journal.parent/".storage-catalog-v1.json"
                with closing(sqlite3.connect(journal.as_uri()+"?mode=ro", uri=True)) as conn:
                    conn.execute("BEGIN")
                    digest = sha256()
                    count = total = 0
                    for (payload,) in conn.execute("SELECT payload FROM journal ORDER BY sequence"):
                        total += len(payload)
                        count += 1
                        digest.update(payload)
                    assert count == rows
                    for audit in (False, True):
                        expected = None
                        samples = {key: [] for key in bins}
                        for pair in range(args.pairs+1):
                            for label in list(bins)[::1 if pair % 2 else -1]:
                                index.unlink(missing_ok=True)
                                with Client(bins[label], args.cpu) as c:
                                    cpu_start = c.cpu()
                                    start = time.perf_counter_ns()
                                    result = c.call("list", audit=audit, **listing)
                                    elapsed = time.perf_counter_ns()-start
                                    cpu_ticks = c.cpu()-cpu_start
                                assert result["sessions"][0]["message_count"] == rows
                                if audit:
                                    assert not index.exists()
                                    written = None
                                else:
                                    written = index.read_bytes()
                                    parsed = json.loads(written)
                                    assert parsed["data"]["fingerprint"] == digest.hexdigest()
                                    assert parsed["data"]["extent"] == rows
                                if expected is None:
                                    expected = (result, written)
                                assert (result, written) == expected, (case, audit, label)
                                if pair:
                                    csv_out.writerow((case, pair, label, int(audit), rows, total, elapsed, cpu_ticks))
                                    samples[label].append(elapsed/1e6)
                        out.flush()
                        print(f"{case} audit={audit} rows={rows} payload={total} "
                              f"stock={statistics.median(samples['stock']):.3f}ms "
                              f"candidate={statistics.median(samples['candidate']):.3f}ms; "
                              "exact response/index parity", flush=True)


if __name__ == "__main__":
    main()
