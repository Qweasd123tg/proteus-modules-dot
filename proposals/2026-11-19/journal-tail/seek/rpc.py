"""Minimal real SDK v3 peer and deterministic synthetic commit fixture."""
import json
import subprocess
import uuid
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
