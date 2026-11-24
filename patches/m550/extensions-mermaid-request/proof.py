"""Reproduce the native Mermaid transport proof using an exact local source archive."""
import argparse
import hashlib
import json
import os
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
    args.add_argument("--baseline", type=Path, required=True, help="exact 151-entry Extensions-M350-native-inputs.tar.gz")
    args.add_argument("--height", type=Path, required=True, help="exact #596 source.patch")
    args.add_argument("--widgets", type=Path, required=True, help="exact #598 source.patch")
    args.add_argument("--vendor", type=Path, required=True, help="verified Cargo directory source from the original lock")
    args.add_argument("--work", type=Path, required=True, help="writable scratch parent")
    a = args.parse_args()
    pins = json.loads((here/"receipt.json").read_bytes())
    archive = a.baseline.resolve(strict=True)
    assert sha(archive.read_bytes()) == pins["m350_native_sha256"]
    assert sha(a.height.read_bytes()) == pins["accepted_patches"]["596"]
    assert sha(a.widgets.read_bytes()) == pins["accepted_patches"]["598"]
    patch = here/"source.patch"
    assert sha(patch.read_bytes()) == pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="mermaid-native-", dir=a.work.resolve(strict=True)) as tmp:
        runroot=Path(tmp)
        workspace=runroot/"source";workspace.mkdir()
        with tarfile.open(archive) as t:
            # Archive SHA is pinned above, including tracked package license symlinks.
            assert len(t.getmembers()) == 151
            t.extractall(workspace, filter="data")
        env={**os.environ,"CARGO_TARGET_DIR":str(runroot/"target"),
             "CARGO_HOME":str(runroot/"cargo-home"),"CARGO_NET_OFFLINE":"true",
             "CARGO_INCREMENTAL":"0","CARGO_PROFILE_TEST_DEBUG":"0"}
        def call(cmd):
            subprocess.run(cmd, cwd=workspace, env=env, timeout=180, check=True)
        def apply(patch, *opts):
            for extra in [["--check"], []]:
                call(["git","apply",*opts,*extra,str(patch.resolve(strict=True))])
        cargo = ["cargo", "--config", 'source.crates-io.replace-with="verified-vendor"',
                 "--config", 'source.verified-vendor.directory='+json.dumps(str(a.vendor.resolve(strict=True))),
                 "test","--locked","--offline","-p","extension-mermaid-render"]
        apply(a.height); apply(a.widgets)
        base = mode_bytes(workspace)
        svg = workspace/"packages/mermaid-render"
        worker = svg/"src/worker.rs"
        def case(label):
            call(cargo+["--","--skip","different_sessions_share_one_worker_and_last_close_and_eof_reap_it"])
            out = runroot/(label+".ndjson")
            call(["python3",str(here/"wire_proof.py"),str(runroot/"target/debug/mermaid-render"),str(svg),str(out)])
            return out.read_bytes()
        stock = case("stock")
        apply(patch)
        after = mode_bytes(workspace)
        assert after.keys()==base.keys()
        actual = {p for p in base if base[p]!=after[p]}
        assert actual == pins["targets"].keys()
        for p in actual:
            assert [sha(base[p][1]), sha(after[p][1])] == pins["targets"][p]["sha256"]
        future = case("future")
        assert stock == future and len(stock)==pins["wire"]["bytes"]
        assert sha(stock)==pins["wire"]["sha256"]
        w=worker.read_bytes();worker.write_bytes(w+(here/"ownership-proof.rs").read_bytes())
        call(cargo+["--bin","mermaid-render","m550_exact_key","--","--nocapture"])
        worker.write_bytes(w)
        assert mode_bytes(workspace)==after
        apply(patch, "--reverse")
        assert mode_bytes(workspace)==base

if __name__ == "__main__":
    main()
