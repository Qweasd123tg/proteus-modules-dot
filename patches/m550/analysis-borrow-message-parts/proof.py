"""Reproduce exact M409 native Analysis multipart formatting and exact wire on Linux."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

here = Path(__file__).resolve().parent

def hash_bytes(data):
    return sha256(data).hexdigest()

def snapshot(root):
    return {p.relative_to(root).as_posix(): (
        ("120000", bytes(p.readlink())) if p.is_symlink()
        else ("100755" if p.stat().st_mode & 0o111 else "100644", p.read_bytes()))
        for p in root.rglob("*") if p.is_symlink() or p.is_file()}

def verify(args, pins, tmp):
    work = tmp/"source"
    work.mkdir()
    with tarfile.open(args.baseline) as t:
        assert len(t.getmembers())==pins["input_archive"]["entries"]==468
        t.extractall(work,filter="data")
    with tarfile.open(args.overlay) as t:
        assert t.getnames()==["packages/markdown-render/src/inlines.rs"]
        t.extractall(work,filter="data")
    env = {**os.environ, "CARGO_TARGET_DIR": str(tmp/"target"),
           "CARGO_HOME": str(tmp/"cargo"), "CARGO_NET_OFFLINE": "true",
           "CARGO_BUILD_JOBS":"2","CARGO_INCREMENTAL":"0",
           "CARGO_PROFILE_TEST_DEBUG":"0","CARGO_PROFILE_DEV_DEBUG":"0"}
    def call(cmd):
        subprocess.run(cmd,cwd=work,env=env,timeout=240,check=True)
    cargo = ["cargo","--config",'source.crates-io.replace-with="locked-local"',
             "--config","source.locked-local.directory="+json.dumps(str(args.vendor.resolve(strict=True)))]
    def apply(*flags):
        for dry in (["--check"],[]):
            call(["git","apply",*flags,*dry,str(here/"source.patch")])
    f = work/pins["path"]
    binary = tmp/"target/debug/analysis"
    def case(label):
        print(label,flush=True)
        for op in ("test","build"):
            call(cargo+[op,"--locked","--offline","-p","extension-analysis"])
        raw=tmp/(label+"-wire.ndjson")
        call(["python3",str(here/"wire-proof.py"),str(binary),str(raw)])
        saved=f.read_bytes()
        stats=tmp/(label+"-allocator.log")
        with_meter=tmp/(label+"-meter.ndjson")
        try:
            call(["python3",str(here/"inject.py"),str(f),str(here/"allocator-proof.rs")])
            call(cargo+["build","--locked","--offline","-p","extension-analysis"])
            call(["python3",str(here/"wire-proof.py"),str(binary),str(with_meter),str(stats)])
        finally:
            f.write_bytes(saved)
        blob=raw.read_bytes()
        assert blob==with_meter.read_bytes()
        raw.unlink(); with_meter.unlink()
        numbers=[list(map(int,line.split()[1:])) for line in stats.read_text().splitlines()]
        print("allocator",json.dumps(numbers),flush=True)
        return blob, numbers

    base=snapshot(work)
    target=pins["path"]
    assert len(base)==468
    a, before = case("baseline")
    assert snapshot(work)==base
    apply()
    patched=snapshot(work)
    assert patched.keys()==base.keys()
    assert [n for n,b in base.items() if patched[n]!=b]==[target]
    assert base[target][0]==patched[target][0]==pins["path_mode"]
    assert [hash_bytes(b[1]) for b in (base[target],patched[target])]==pins["path_before_after_sha256"]
    assert hash_bytes(base["Cargo.lock"][1])==hash_bytes(patched["Cargo.lock"][1])==pins["cargo_lock_sha256"]
    b, after = case("proposed")
    assert a==b
    assert [len(a.splitlines()),len(a),hash_bytes(a)]==[pins["wire"][k] for k in ("frames","bytes","sha256")]
    assert [before,after]==pins["allocator"]["before_after"]
    assert len(before)==len(after)==15
    for index in (0,5):
        old,new=before[index],after[index]
        assert old[1]-new[1]>=2_360_000
        assert old[3]-new[3]>=880_000
    for old,new in zip(before,after):
        assert old[2]==new[2]  # exact logical retained result
        assert all(n<=o for o,n in zip(old,new))
    for index in (2,3,7,8,12,13):
        assert before[index]==after[index]  # raw-JSON and single-text controls
    apply("--reverse")
    assert snapshot(work)==base
    print("Exact inverse restores all 468 entries; all raw frames, multipart controls and allocation differential verified.")

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    for flag in ("baseline","overlay","vendor","work"):
        cli.add_argument("--"+flag,type=Path,required=True)
    args=cli.parse_args()
    pins=json.loads((here/"receipt.json").read_bytes())
    assert hash_bytes(args.baseline.read_bytes())==pins["input_archive"]["sha256"]
    assert hash_bytes(args.overlay.read_bytes())==pins["verified_overlay"]["sha256"]
    assert hash_bytes((here/"source.patch").read_bytes())==pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="analysis-multipart-native-",dir=args.work.resolve(strict=True)) as td:
        verify(args,pins,Path(td))

if __name__=="__main__":
    main()
