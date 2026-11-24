"""Exact M411 Files/SDK shared preview replay (Linux x86_64)."""
import argparse
from hashlib import sha256
import json
import os
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
    for archive, guard in (
        (args.baseline,None), (args.overlay409,"packages/markdown-render/src/inlines.rs"),
        (args.overlay411,"packages/analysis/src/text.rs"),
    ):
        with tarfile.open(archive) as t:
            if guard: assert t.getnames()==[guard]
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
    print("Exact forward/inverse restores all 468 M411 entries.",flush=True)
    if args.source_only:
        return

    cargo=["cargo","--config",'source.crates-io.replace-with="locked-local"',
           "--config","source.locked-local.directory="+json.dumps(str(args.vendor.resolve(strict=True)))]
    binary=tmp/"target/debug/files"
    f=work/"packages/files/src/main.rs"

    def case(label):
        print(label,flush=True)
        cli=(["--workspace","--","--skip","different_sessions_share_one_worker_and_last_close_and_eof_reap_it"]
             if args.workspace else ["-p","proteus-extension","-p","extension-files"])
        call(cargo+["test","--locked","--offline"]+cli)
        call(cargo+["build","--locked","--offline","-p","extension-files"])
        raw=tmp/(label+"-wire.ndjson")
        call(["python3",str(HERE/"wire-proof.py"),str(binary),str(raw)])
        witness=tmp/(label+"-meter.ndjson")
        log=tmp/(label+"-allocator.log")
        saved=f.read_bytes()
        try:
            call(["python3",str(HERE/"inject.py"),str(f),str(HERE/"allocator-proof.rs")])
            call(cargo+["build","--locked","--offline","-p","extension-files"])
            call(["python3",str(HERE/"wire-proof.py"),str(binary),str(witness),str(log)])
        finally:
            f.write_bytes(saved)
        blob=raw.read_bytes()
        assert blob==witness.read_bytes()
        raw.unlink();witness.unlink()
        runs=[]
        for line in log.read_text().splitlines():
            name,*stats=line.split()[1:]
            runs.append([name,*map(int,stats)])
        print("allocator",json.dumps(runs),flush=True)
        return blob,runs

    a, old=case("baseline")
    assert snapshot(work)==base
    apply()
    assert snapshot(work)==patched
    b, new=case("proposed")
    assert a==b
    assert [len(a.splitlines()),len(a),digest(a)]==[pins["wire"][k] for k in ("frames","bytes","sha256")]
    assert [r[0] for r in old]==[r[0] for r in new] and len(old)==13
    # Cold connection bookkeeping can shift small allocator deltas. The
    # resident sibling cases make no HTTP requests and have a stable margin.
    opened_old=sum(r[3] for r in old[:3]);opened_new=sum(r[3] for r in new[:3])
    assert opened_old-opened_new>=1_430_000 and opened_new<520_000
    for i in (1,2):
        assert old[i][3]-new[i][3]>480_000
    for i in (1,2,4,5,6,7,8):
        assert old[i][2]-new[i][2]>480_000
        assert old[i][4]-new[i][4]>480_000
    assert abs(old[0][4]-new[0][4])<8192  # unchanged dominant parse peak
    assert snapshot(work)==patched
    apply("--reverse")
    assert snapshot(work)==base
    print("Native wire, cache lifecycle and retained allocation differential verified.")

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    for flag in ("baseline","overlay409","overlay411","work"):
        cli.add_argument("--"+flag,type=Path,required=True)
    cli.add_argument("--vendor",type=Path)
    cli.add_argument("--source-only",action="store_true")
    cli.add_argument("--workspace",action="store_true")
    args=cli.parse_args()
    assert args.source_only or args.vendor is not None
    pins=json.loads((HERE/"receipt.json").read_bytes())
    assert digest(args.baseline.read_bytes())==pins["input_archive"]["sha256"]
    assert [digest(p.read_bytes()) for p in (args.overlay409,args.overlay411)]==[
        item["sha256"] for item in pins["verified_overlays"]]
    assert digest((HERE/"source.patch").read_bytes())==pins["patch_sha256"]
    with tempfile.TemporaryDirectory(prefix="files-preview-native-",dir=args.work.resolve(strict=True)) as td:
        verify(args,pins,Path(td))

if __name__=="__main__":
    main()
