#!/usr/bin/env python3
"""Local SDK fixture: fresh workers with ordinary committed rows (Linux)."""
import json
import os
from pathlib import Path
import signal
import subprocess
import uuid


def u(i):
    return str(uuid.UUID(int=i))


class Client:
    def __init__(self, binary, cpu):
        self.child = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        os.sched_setaffinity(self.child.pid, {cpu})
        self.seq = -1
        self.export = dict(slot="session_storage", module_id="sqlite")
        self.rpc("initialize", dict(protocol_version="v3", component_id="sqlite-page-bench",
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

