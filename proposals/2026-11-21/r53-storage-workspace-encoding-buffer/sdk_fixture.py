#!/usr/bin/env python3
"""Local SDK catalog fixture: fresh workers with ordinary committed rows (Linux)."""
import json
import os
import signal
import subprocess
import uuid


def u(i):
    return str(uuid.UUID(int=i))


class Client:
    def __init__(self, binary, cpu, backend):
        self.child = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.sched_setaffinity(self.child.pid, {cpu})
        self.seq = -1
        self.export = dict(slot="session_storage", module_id=backend)
        self.rpc("initialize", dict(protocol_version="v3", component_id="workspace-catalog-alloc",
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

    def allocation(self):
        signal.alarm(45)
        try:
            prefix, count, requested = self.child.stderr.readline().split()
        finally:
            signal.alarm(0)
        assert prefix == b"R53", prefix
        return int(count), int(requested)

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
        stderr = self.child.stderr.read()
        self.child.stderr.close()
        assert self.child.returncode == 0, (self.child.returncode, stderr)

