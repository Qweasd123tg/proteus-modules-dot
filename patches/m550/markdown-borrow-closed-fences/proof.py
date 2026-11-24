"""Reproduce the native Markdown fence ownership proof using an exact local source archive."""
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
    args.add_argument("--baseline", type=Path, required=True, help="exact 151-entry Extensions-M380-native-inputs.tar.gz")
    args.add_argument("--vendor", type=Path, required=True, help="verified Cargo directory source from the original lock")
    args.add_argument("--work", type=Path, required=True, help="writable scratch parent")
    a = args.parse_args()
    pins = json.loads((here/"receipt.json").read_bytes())
    archive = a.baseline.resolve(strict=True)
    assert sha(archive.read_bytes()) == pins["m380_native_sha256"]
    patch = here/"source.patch"
    assert sha(patch.read_bytes()) == pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="markdown-native-", dir=a.work.resolve(strict=True)) as tmp:
        runroot=Path(tmp)
        workspace=runroot/"source";workspace.mkdir()
        with tarfile.open(archive) as t:
            # Archive SHA is pinned above, including tracked package license symlinks.
            assert len(t.getmembers()) == 151
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
        targets = pins["targets"]
        f = workspace/"packages/markdown-render/src/fences.rs"
        test_source = (here/"allocator-proof.rs").read_bytes()
        def case(label, direct):
            call(cargo)
            out = runroot/(label+".ndjson")
            call(["python3",str(here/"wire-proof.py"),str(runroot/"target/debug/markdown-render"),str(out)])
            saved = f.read_bytes()
            f.write_bytes(saved+test_source)
            alloc = call(cargo+["--bin","markdown-render","m550_fence_ownership","--","--nocapture"],
                         extra={"EXPECT_DIRECT_SOURCE": "yes" if direct else "no"}, capture=True)
            f.write_bytes(saved)
            m = re.search(r"^parsed (\d+) Requests \{ allocs: (\d+), bytes: (\d+), live: (\d+), peak: (\d+) \}$", alloc, re.M)
            assert m is not None
            return out.read_bytes(), tuple(map(int, m.groups()))
        stock, before = case("stock", False)
        assert mode_bytes(workspace)==base
        apply(patch)
        after = mode_bytes(workspace)
        assert after.keys()==base.keys()
        assert {p for p in base if base[p]!=after[p]} == targets.keys()
        for target, detail in targets.items():
            assert base[target][0] == after[target][0] == detail["mode"]
            assert [sha(base[target][1]),sha(after[target][1])] == detail["sha256"]
        assert sha(after["Cargo.lock"][1]) == pins["cargo_lock_sha256"]
        future, proposed = case("future", True)
        assert stock == future and len(stock)==pins["wire"]["bytes"]
        assert sha(stock)==pins["wire"]["sha256"]
        count, allocs, bytes_requested, live, peak = before
        assert proposed == (count, allocs - 2, bytes_requested - count, live - count, peak)
        assert mode_bytes(workspace)==after
        apply(patch, "--reverse")
        assert mode_bytes(workspace)==base
        print("Exact forward/inverse, native package, wire bytes and allocator differential verified.")

if __name__ == "__main__":
    main()
