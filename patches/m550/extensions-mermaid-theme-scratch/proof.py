"""Reproduce the Mermaid theme-materializer proof using an exact local source archive."""
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
    args.add_argument("--baseline", type=Path, required=True, help="exact 151-entry Extensions-M362-native-inputs.tar.gz")
    args.add_argument("--references", type=Path, required=True, help="exact #607 source.patch to finish the Extensions projection of M368")
    args.add_argument("--vendor", type=Path, required=True, help="verified Cargo directory source from the original lock")
    args.add_argument("--work", type=Path, required=True, help="writable scratch parent")
    a = args.parse_args()
    pins = json.loads((here/"receipt.json").read_bytes())
    archive = a.baseline.resolve(strict=True)
    assert sha(archive.read_bytes()) == pins["m362_native_sha256"]
    assert sha(a.references.read_bytes()) == pins["accepted_patch_607_sha256"]
    patch = here/"source.patch"
    assert sha(patch.read_bytes()) == pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="mermaid-native-", dir=a.work.resolve(strict=True)) as tmp:
        runroot=Path(tmp)
        workspace=runroot/"source";workspace.mkdir()
        with tarfile.open(archive) as t:
            assert len(t.getmembers()) == 151
            t.extractall(workspace, filter="data")
        env={**os.environ,"CARGO_TARGET_DIR":str(runroot/"target"),
             "CARGO_HOME":str(runroot/"cargo-home"),"CARGO_NET_OFFLINE":"true",
             "CARGO_INCREMENTAL":"0","CARGO_PROFILE_TEST_DEBUG":"0"}
        def call(cmd, cwd=workspace, capture=False):
            p = subprocess.run(cmd, cwd=cwd, env=env, timeout=180, check=True,
                               text=True, capture_output=capture)
            if capture:
                print(p.stdout, end="")
                return p.stdout
        def apply(patch, *opts):
            for extra in [["--check"], []]:
                call(["git","apply",*opts,*extra,str(patch.resolve(strict=True))])
        apply(a.references)
        cargo = ["cargo", "--config", 'source.crates-io.replace-with="verified-vendor"',
                 "--config", 'source.verified-vendor.directory='+json.dumps(str(a.vendor.resolve(strict=True))),
                 "test","--locked","--offline","-p","extension-mermaid-render"]
        call(cargo+["--","--skip","different_sessions_share_one_worker_and_last_close_and_eof_reap_it"])
        binary=runroot/"target/debug/mermaid-render"
        svg = workspace/"packages/mermaid-render"
        base = mode_bytes(workspace)
        def case(label):
            call(["node","--test","tests/worker.test.mjs"],cwd=svg)
            wire = runroot/(label+".ndjson")
            call(["python3",str(here/"wire-proof.py"),str(binary),str(svg),str(wire)])
            materialized = runroot/(label+".json")
            count = call(["node",str(here/"materialize-proof.mjs"),str(svg),str(materialized)],capture=True)
            maps={k:int(v) for k,v,_ in (row.split() for row in count.splitlines() if not row.startswith("materialized"))}
            assert maps==pins["map_constructor_calls"][label]
            return {"materialized": materialized.read_bytes(), "rust_to_node": wire.read_bytes()}
        stock = case("stock")
        apply(patch)
        after = mode_bytes(workspace)
        target=pins["target"]["path"]
        assert after.keys()==base.keys()
        assert {p for p in base if base[p]!=after[p]} == {target}
        assert base[target][0]==after[target][0]==pins["target"]["mode"]
        assert [sha(base[target][1]),sha(after[target][1])] == pins["target"]["sha256"]
        assert sha(after["Cargo.lock"][1])==pins["cargo_lock_sha256"]
        future = case("candidate")
        assert stock==future
        for kind,b in stock.items():
            assert len(b)==pins[kind]["bytes"] and sha(b)==pins[kind]["sha256"]
        apply(patch, "--reverse")
        assert mode_bytes(workspace)==base
        print("Exact native worker wire, materialization, operation counts and rollback verified.")

if __name__ == "__main__":
    main()
