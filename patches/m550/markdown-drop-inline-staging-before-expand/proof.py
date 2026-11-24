"""Exact M417 Markdown rewrite lifetime and native parity (Linux x86_64)."""
import argparse
from hashlib import sha256
import json
import os
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent

def digest(data):
    return sha256(data).hexdigest()

def snapshot(root):
    return {p.relative_to(root).as_posix(): (
        ("120000", bytes(p.readlink())) if p.is_symlink()
        else ("100755" if p.stat().st_mode & 0o111 else "100644", p.read_bytes()))
        for p in root.rglob("*") if p.is_symlink() or p.is_file()}

def verify(args, pins, tmp):
    work = tmp/"source"
    work.mkdir()
    overlays=(args.overlay409,args.overlay411,args.overlay414,args.overlay417)
    for archive,guard in [
        (args.baseline,None),
        *[(archive,meta["members"]) for archive,meta in zip(overlays,pins["verified_overlays"])],
    ]:
        with tarfile.open(archive) as t:
            if guard: assert set(t.getnames())==set(guard)
            else: assert len(t.getmembers())==pins["input_archive"]["entries"]==468
            t.extractall(work,filter="data")
    env={**os.environ,"CARGO_TARGET_DIR":str(tmp/"target"),"CARGO_HOME":str(tmp/"cargo"),
         "CARGO_NET_OFFLINE":"true","CARGO_BUILD_JOBS":"2","CARGO_INCREMENTAL":"0",
         "CARGO_PROFILE_TEST_DEBUG":"0","CARGO_PROFILE_DEV_DEBUG":"0"}
    def call(cmd):
        subprocess.run(cmd,cwd=work,env=env,timeout=240,check=True)
    patch=HERE/"source.patch"
    def apply(*flags):
        for dry in (["--check"],[]):
            call(["git","apply",*flags,*dry,str(patch)])
    base=snapshot(work)
    apply()
    patched=snapshot(work)
    paths=pins["paths"]
    assert len(base)==len(patched)==468 and base.keys()==patched.keys()
    assert {k for k,old in base.items() if patched[k]!=old}==paths.keys()
    for name, detail in paths.items():
        assert base[name][0]==patched[name][0]==detail["mode"]
        assert [digest(b[1]) for b in (base[name],patched[name])]==detail["before_after_sha256"]
    assert digest(base["Cargo.lock"][1])==digest(patched["Cargo.lock"][1])==pins["cargo_lock_sha256"]
    apply("--reverse")
    assert snapshot(work)==base
    print("Exact forward/inverse restores all 468 M417 entries.",flush=True)
    if not args.native:
        return
    assert shutil.disk_usage(tmp).free>=args.min_free_mib*2**20, "not enough disk for serial native build"

    cargo=["cargo","--config",'source.crates-io.replace-with="locked-local"',
           "--config","source.locked-local.directory="+json.dumps(str(args.vendor.resolve(strict=True)))]
    binary=tmp/"target/debug/markdown-render"
    f=work/"packages/markdown-render/src/inlines.rs"

    def case(label):
        print(label,flush=True)
        # The package's subprocess integration tests build its executable.
        call(cargo+["test","--locked","--offline","-p","extension-markdown-render"])
        raw=tmp/(label+"-wire.ndjson")
        call(["python3",str(HERE/"wire-proof.py"),str(binary),str(raw)])
        witness=tmp/(label+"-meter.ndjson")
        log=tmp/(label+"-allocator.log")
        saved=f.read_bytes()
        try:
            call(["python3",str(HERE/"inject.py"),str(f),str(HERE/"allocator-proof.rs")])
            call(cargo+["build","--locked","--offline","-p","extension-markdown-render"])
            call(["python3",str(HERE/"wire-proof.py"),str(binary),str(witness),str(log)])
        finally:
            f.write_bytes(saved)
        blob=raw.read_bytes()
        assert blob==witness.read_bytes()
        raw.unlink();witness.unlink()
        runs=[list(map(int,line.split()[1:])) for line in log.read_text().splitlines()]
        print("allocator",json.dumps(runs),flush=True)
        return blob,runs

    a, old=case("baseline")
    assert snapshot(work)==base
    apply()
    assert snapshot(work)==patched
    b, new=case("proposed")
    assert a==b
    assert [len(a.splitlines()),len(a),digest(a)]==(
        [pins["wire_expected"][k] for k in ("frames","bytes","sha256")]
    )
    print("verified_exact_wire",len(a.splitlines()),len(a),digest(a),flush=True)
    assert len(old)==len(new)==8
    # Counters hold layout bytes relative to inlines::render entry; the
    # reduced peaks have to show up in the real route, not just the copy count.
    for i,(stock,future) in enumerate(zip(old,new)):
        assert stock[:3]==future[:3], (i,stock,future)
        assert future[3]<=stock[3] and future[4]<=stock[4] and future[5]<=stock[5], (i,stock,future)
    assert old[6]==new[6] and old[6][4:]==[-1,-1]  # disabled provider
    for i in (0,1):
        assert old[i][4]-new[i][4]>=1_100_000, (i,old[i],new[i])
        assert old[i][3]-new[i][3]>=500_000, (i,old[i],new[i])
    print("verified_native_rewrite_metrics",json.dumps([old,new]),flush=True)
    apply("--reverse")
    assert snapshot(work)==base
    print("Native wire, inline limits and rewrite lifetime differential verified.")

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    for flag in ("baseline","overlay409","overlay411","overlay414","overlay417","work"):
        cli.add_argument("--"+flag,type=Path,required=True)
    cli.add_argument("--vendor",type=Path)
    cli.add_argument("--native",action="store_true")
    cli.add_argument("--min-free-mib",type=int,default=110)
    args=cli.parse_args()
    assert not args.native or args.vendor is not None
    pins=json.loads((HERE/"receipt.json").read_bytes())
    assert digest(args.baseline.read_bytes())==pins["input_archive"]["sha256"]
    assert [digest(p.read_bytes()) for p in (args.overlay409,args.overlay411,args.overlay414,args.overlay417)]==[
        item["sha256"] for item in pins["verified_overlays"]]
    assert digest((HERE/"source.patch").read_bytes())==pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="markdown-rewrite-native-",dir=args.work.resolve(strict=True)) as td:
        verify(args,pins,Path(td))

if __name__=="__main__":
    main()
