#!/usr/bin/env python3
"""Linux/macOS: exercise only healthy shared writer uses, in a disposable directory."""
import argparse
import hashlib
import json
import signal
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


def timeout(_sig, _frame):
    raise TimeoutError("SDK worker did not respond")


@contextmanager
def worker(binary, kind):
    with subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
        sequence = 0
        def rpc(method, params):
            nonlocal sequence
            ident = f"h:1:{sequence}"
            sequence += 1
            json.dump(dict(jsonrpc="2.0", id=ident, method=method, params=params), child.stdin)
            child.stdin.write("\n")
            child.stdin.flush()
            signal.alarm(20)
            try:
                response = json.loads(child.stdout.readline())
            finally:
                signal.alarm(0)
            assert response["id"] == ident and "result" in response, response
            return response["result"]
        binding = dict(slot="session_storage", module_id=kind)
        def call(operation, **kwargs):
            return rpc("execute", dict(export=binding,
                lineage=dict(root_invocation_id=f"h:1:{sequence}", parent_invocation_id=None, depth=0),
                params=dict(operation=operation, **kwargs)))
        try:
            rpc("initialize", dict(protocol_version="v3", component_id="storage-lifecycle-test",
                exports=[dict(**binding, contract_version="v2", composition="select_one",
                              module_config={}, host_features=[])]))
            yield call
        finally:
            child.stdin.close()
            try:
                child.wait(5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            assert child.returncode == 0, child.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    binary = parser.parse_args().binary.resolve(strict=True)
    signal.signal(signal.SIGALRM, timeout)
    print("worker SHA-256:", hashlib.sha256(binary.read_bytes()).hexdigest())
    for kind in ("jsonl", "sqlite"):
        with tempfile.TemporaryDirectory() as tmp, worker(binary, kind) as owner, worker(binary, kind) as other:
            root = Path(tmp)
            (root/"workspace").mkdir()
            descriptor = owner("create", config_root=str(root/"config"), workspace_path=str(root/"workspace"),
                               session_id=str(uuid.uuid4()), parent_session_id=None)["descriptor"]
            session = descriptor["session"]
            a = owner("acquire_writer", session=session)
            b = owner("acquire_writer", session=session)
            assert a["lease"]["generation"] == b["lease"]["generation"]
            owner("release_writer", lease=a["lease"])
            owner("hibernate_writer", lease=b["lease"])
            c = owner("acquire_writer", session=session)
            assert len({x["lease"]["token"] for x in (a, b, c)}) == 3
            assert a["revision"] == b["revision"] == c["revision"]
            owner("release_writer", lease=c["lease"])
            owner("release_writer", lease=b["lease"])
            next_owner = other("acquire_writer", session=session)
            assert next_owner["revision"] == a["revision"]
            other("release_writer", lease=next_owner["lease"])
            print(kind, "3 distinct shared handles, hibernate/release, second live process acquired: PASS")


if __name__ == "__main__":
    main()
