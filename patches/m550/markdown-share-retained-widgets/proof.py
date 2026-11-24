"""Exact M398 forward/inverse, locked bundle, native raw wire and allocator replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

here = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

def snapshot(root):
    return {p.relative_to(root).as_posix(): (
        ("120000", os.fsencode(os.readlink(p))) if p.is_symlink()
        else ("100755" if p.stat().st_mode & 0o111 else "100644", p.read_bytes())
    ) for p in root.rglob("*") if p.is_file() or p.is_symlink()}

def replay(a, pins, runroot):
    work = runroot/"src"
    work.mkdir()
    with tarfile.open(a.baseline) as t:
        assert len(t.getmembers()) == 467
        t.extractall(work, filter="data")
    env = {**os.environ, "CARGO_TARGET_DIR": str(runroot/"target"),
           "CARGO_HOME": str(runroot/"cargo"), "CARGO_NET_OFFLINE": "true", "CARGO_BUILD_JOBS": "2",
           "CARGO_INCREMENTAL": "0", "CARGO_PROFILE_TEST_DEBUG": "0", "CARGO_PROFILE_DEV_DEBUG": "0"}
    def call(cmd):
        subprocess.run(cmd, cwd=work, env=env, timeout=240, check=True)
    patch = here/"source.patch"
    def apply(*opts):
        call(["git","apply", *opts, "--check", str(patch)])
        call(["git","apply", *opts, str(patch)])
    cargo = ["cargo", "--config", 'source.crates-io.replace-with="verified-vendor"', "--config",
             "source.verified-vendor.directory="+json.dumps(str(a.vendor.resolve(strict=True)))]
    def check(label):
        call(cargo + ["test", "--locked", "--offline", "--workspace", "--",
                      "--skip", "different_sessions_share_one_worker_and_last_close_and_eof_reap_it"])
        call(cargo + ["build", "--locked", "--offline", "-p", "extension-analysis"])
        md = runroot/"target/debug/markdown-render"
        analysis = runroot/"target/debug/analysis"
        outs = [runroot/f"{label}-{name}.ndjson" for name in ("markdown","analysis","meter")]
        for script, binpath, output in zip(("wire-proof.py","analysis-wire-proof.py"), (md,analysis),outs):
            call(["python3",str(here/script),str(binpath),str(output)])
        f = work/"packages/markdown-render/src/main.rs"
        main = f.read_bytes()
        entry = b'    fn render(&mut self, host: &mut Host, view: &str, surface: Surface, _: Option<&str>) -> Result {\n'
        assert main.count(entry) == 1
        f.write_bytes(main.replace(entry,entry+b'        let _phase = m550_wire_alloc::start();\n')
                      +(here/"allocator-proof.rs").read_bytes())
        try:
            call(cargo + ["build", "--locked", "--offline", "-p", "extension-markdown-render"])
            stats = runroot/f"{label}-alloc.txt"
            call(["python3",str(here/"wire-proof.py"),str(md),str(outs[2]),str(stats)])
        finally:
            f.write_bytes(main)
        assert outs[0].read_bytes() == outs[2].read_bytes()
        measured = [list(map(int,line.split()[1:])) for line in stats.read_text().splitlines()]
        by_route = {"markdown": outs[0].read_bytes(), "analysis": outs[1].read_bytes()}
        for generated in outs:
            generated.unlink()
        print(label, "allocator [calls, request bytes, end delta, logical peak delta]", json.dumps(measured), flush=True)
        call(cargo + ["clean", "-q"])
        return by_route, measured

    base = snapshot(work)
    stock, old = check("stock")
    assert snapshot(work) == base
    apply()
    patched = snapshot(work)
    changes = {p for p in base.keys() | patched.keys() if base.get(p) != patched.get(p)}
    assert changes == set(pins["paths"])
    for name, ids in pins["paths"].items():
        assert [([entry[0],sha(entry[1])] if entry else None)
                for entry in (base.get(name), patched.get(name))] == ids
    future, new = check("proposed")
    assert stock == future
    for route, data in stock.items():
        actual = [len(data.splitlines()),len(data),sha(data)]
        assert actual == pins["wire"][route], actual
    for i in (0,2,9,10):
        assert old[i][1]-new[i][1] > 700_000
    # Summed net logical bytes over consecutive successful edits, starting at
    # the same fresh view; excludes the already-installed Host input frame.
    for start, stop, floor in ((0,1,700_000),(0,3,700_000),(8,11,1_500_000)):
        improvement = sum(s[2]-p[2] for s,p in zip(old[start:stop],new[start:stop]))
        assert improvement > floor, (start, stop, improvement)
        print("logical retained bytes reduction through reply",stop,improvement)
    for warm in (2,10):
        assert old[warm][3]-new[warm][3] > 700_000
    assert snapshot(work) == patched
    apply("--reverse")
    assert snapshot(work) == base
    print("Exact forward/inverse (467 base entries), locked workspace, raw wire and allocator verified.")

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "vendor", "work"):
        ap.add_argument("--"+name, type=Path, required=True)
    a = ap.parse_args()
    pins = json.loads((here/"receipt.json").read_bytes())
    assert sha(a.baseline.read_bytes()) == pins["m398_source_sha256"]
    assert sha((here/"source.patch").read_bytes()) == pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="markdown-share-native-",dir=a.work.resolve(strict=True)) as tmp:
        replay(a, pins, Path(tmp))

if __name__ == "__main__":
    main()
