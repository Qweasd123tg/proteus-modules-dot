"""Reproduce the native Markdown invalidation ownership proof using an exact local source archive."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tarfile
import tempfile

here = Path(__file__).resolve().parent

def sha(b):
    return hashlib.sha256(b).hexdigest()

def mode_bytes(root):
    rows = {}
    for path in sorted(root.rglob("*")):
        p = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows[p] = ("120000", os.fsencode(os.readlink(path)))
        elif path.is_file():
            rows[p] = ("100755" if path.stat().st_mode & 0o111 else "100644", path.read_bytes())
    return rows

def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--baseline", type=Path, required=True, help="exact 467-entry Extensions-M391-source.tar.gz")
    args.add_argument("--vendor", type=Path, required=True, help="verified Cargo directory source from the original lock")
    args.add_argument("--work", type=Path, required=True, help="writable scratch parent")
    a = args.parse_args()
    pins = json.loads((here/"receipt.json").read_bytes())
    archive = a.baseline.resolve(strict=True)
    assert sha(archive.read_bytes()) == pins["m391_source_sha256"]
    patch = here/"source.patch"
    assert sha(patch.read_bytes()) == pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="markdown-invalidate-native-", dir=a.work.resolve(strict=True)) as tmp:
        runroot=Path(tmp)
        workspace=runroot/"source";workspace.mkdir()
        with tarfile.open(archive) as t:
            # Archive SHA is pinned above, including tracked package license symlinks.
            assert len(t.getmembers()) == 467
            t.extractall(workspace, filter="data")
        env={**os.environ,"CARGO_TARGET_DIR":str(runroot/"target"),
             "CARGO_HOME":str(runroot/"cargo-home"),"CARGO_NET_OFFLINE":"true",
             "CARGO_INCREMENTAL":"0","CARGO_PROFILE_TEST_DEBUG":"0"}
        def call(cmd, extra=None, capture=False):
            result = subprocess.run(cmd, cwd=workspace, env={**env, **(extra or {})},
                                    timeout=180, check=True, text=True, capture_output=capture)
            if capture:
                print(result.stdout, end="")
                return result.stdout
        def apply(patch, *opts):
            for extra in [["--check"], []]:
                call(["git","apply",*opts,*extra,str(patch.resolve(strict=True))])
        cargo = ["cargo", "--config", 'source.crates-io.replace-with="verified-vendor"',
                 "--config", 'source.verified-vendor.directory='+json.dumps(str(a.vendor.resolve(strict=True))),
                 "test","--locked","--offline","-p","extension-markdown-render"]
        base = mode_bytes(workspace)
        target = pins["target"]["path"]
        f = workspace/target
        test_source = (here/"allocator-proof.rs").read_bytes()
        def case(label):
            call(cargo)
            out = runroot/(label+".ndjson")
            call(["python3",str(here/"wire-proof.py"),str(runroot/"target/debug/markdown-render"),str(out)])
            saved = f.read_bytes()
            f.write_bytes(saved+test_source)
            alloc = call(cargo+["--bin","markdown-render","m550_invalidation_alloc","--","--nocapture"],
                         capture=True)
            f.write_bytes(saved)
            rx = r"(policy|definitions|reuse) (\d+) Requests \{ allocs: (\d+), bytes: (\d+), live: (-?\d+), peak: (\d+) \}$"
            hits = re.findall(rx, alloc, re.M)
            assert len(hits)==3
            return out.read_bytes(), {key: tuple(map(int, args)) for key,*args in hits}
        stock, before = case("stock")
        assert mode_bytes(workspace)==base
        apply(patch)
        after = mode_bytes(workspace)
        assert after.keys()==base.keys()
        assert {p for p in base if base[p]!=after[p]} == {target}
        detail = pins["target"]
        assert base[target][0] == after[target][0] == detail["mode"]
        assert [sha(base[target][1]),sha(after[target][1])] == detail["sha256"]
        assert sha(after["Cargo.lock"][1]) == pins["cargo_lock_sha256"]
        future, proposed = case("future")
        assert stock == future and len(stock)==pins["wire"]["bytes"]
        assert sha(stock)==pins["wire"]["sha256"]
        for phase in ("policy","definitions"):
            assert before[phase][:-1] == proposed[phase][:-1]
            assert before[phase][-1]-proposed[phase][-1] >= before[phase][0]
        assert before["reuse"] == proposed["reuse"]
        assert mode_bytes(workspace)==after
        apply(patch, "--reverse")
        assert mode_bytes(workspace)==base
        print("Exact forward/inverse, native package, wire bytes and allocator differential verified.")

if __name__ == "__main__":
    main()
