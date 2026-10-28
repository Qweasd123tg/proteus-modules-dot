"""Check pinned text identity and execute only the new fake-process controls."""
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def deny_process_network(event, args):
    if event.startswith(("socket.", "subprocess.")) or event in {
        "os.system", "os.posix_spawn", "os.exec", "os.spawn", "os.fork",
        "os.forkpty", "pty.spawn", "os.startfile", "os.startfile/2",
    }:
        raise RuntimeError("Guard rejected process/network event: " + event)


def main():
    sys.addaudithook(deny_process_network)
    for event in ("subprocess.Popen", "socket.connect", "os.system", "os.posix_spawn"):
        try:
            sys.audit(event, "guard self-check, no action")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Guard not active: " + event)
    identity = json.loads((ROOT / "source-identity.json").read_text())
    assert identity["commit"] == "e9ca11aab25f6d3a8d09b79c8c5266c1320af2b6"
    hashes = {}
    for source in identity["sources"]:
        path = ROOT / "snapshot" / source["path"]
        data = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert blob == source["git_blob"], source["path"]
        hashes[source["path"]] = hashlib.sha256(data).hexdigest()
        if path.suffix == ".py":
            ast.parse(data, filename=str(path))
    path = ROOT / "snapshot/scripts/test_release_reuse_hosts.py"
    ast.parse(path.read_bytes(), filename=str(path))
    relative = "scripts/test_release_reuse_hosts.py"
    expected_patch = "diff --git a/" + relative + " b/" + relative + "\nnew file mode 100644\n"
    expected_patch += "".join(difflib.unified_diff(
        [], path.read_text().splitlines(keepends=True),
        fromfile="/dev/null", tofile="b/" + relative,
    ))
    patch_bytes = (ROOT / "reuse-hosts-controls.patch").read_bytes()
    assert patch_bytes == expected_patch.encode(), "Patch differs from tested file"
    spec = importlib.util.spec_from_file_location("new_reuse_host_controls", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    assert suite.countTestCases() == 12, suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    record = {
        "source_commit": identity["commit"],
        "source_sha256": hashes,
        "test_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
        "patch_scope": "Add only scripts/test_release_reuse_hosts.py; no production changes",
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "status": "passed" if result.wasSuccessful() else "failed",
        "process_network_guard": "active; synthetic audit self-checks rejected",
        "scope": "Only newly authored stdlib controls; fake subprocesses; inert temporary files.",
        "not_run": ["Cargo", "product binaries", "real packaging", "existing test suites",
                    "native UI", "portable end-to-end smoke"],
    }
    (ROOT / "validation.json").write_text(json.dumps(record, indent=2) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
