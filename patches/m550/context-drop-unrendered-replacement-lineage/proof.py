"""Exact M420 Context popup lifetime and native parity (Linux x86_64)."""
import argparse
from hashlib import sha1, sha256
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

def git_object(kind, body):
    return sha1(f"{kind} {len(body)}\0".encode() + body).digest()

def tree_oid(entries):
    tree = {}
    for name, (mode, contents) in entries.items():
        *parts, leaf = name.split("/")
        node = tree
        for part in parts:
            node = node.setdefault(os.fsencode(part), {})
        node[os.fsencode(leaf)] = (mode.encode(), git_object("blob", contents))

    def dirname_oid(node):
        keys = sorted(node, key=lambda key: key + (b"/" if isinstance(node[key],dict) else b""))
        items = []
        for key in keys:
            value = node[key]
            mode, oid = (b"40000", dirname_oid(value)) if isinstance(value, dict) else value
            items.append(mode + b" " + key + b"\0" + oid)
        return git_object("tree", b"".join(items))

    return dirname_oid(tree).hex()

def verify(args, pins, tmp):
    work = tmp/"source"
    work.mkdir()
    overlays=(args.overlay409,args.overlay411,args.overlay414,args.overlay417,args.overlay419)
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
    assert [tree_oid(base),tree_oid(patched)]==pins["trees"]
    assert {k for k,old in base.items() if patched[k]!=old}==paths.keys()
    for name, detail in paths.items():
        assert base[name][0]==patched[name][0]==detail["mode"]
        assert [digest(b[1]) for b in (base[name],patched[name])]==detail["before_after_sha256"]
    assert digest(base["Cargo.lock"][1])==digest(patched["Cargo.lock"][1])==pins["cargo_lock_sha256"]
    apply("--reverse")
    assert snapshot(work)==base
    print("Exact forward/inverse restores all 468 M420 Extensions entries (unchanged since M419).",flush=True)
    if not args.native:
        return
    assert shutil.disk_usage(tmp).free>=args.min_free_mib*2**20, "not enough disk for serial native build"

    cargo=["cargo","--config",'source.crates-io.replace-with="locked-local"',
           "--config","source.locked-local.directory="+json.dumps(str(args.vendor.resolve(strict=True)))]
    binary=tmp/"target/debug/context"
    f=work/"packages/context/src/main.rs"

    def case(label):
        print(label,flush=True)
        call(cargo+["test","--locked","--offline","-p","extension-context"])
        call(cargo+["build","--locked","--offline","-p","extension-context"])
        raw=tmp/(label+"-wire.ndjson")
        call(["python3",str(HERE/"wire-proof.py"),str(binary),str(raw)])
        witness=tmp/(label+"-meter.ndjson")
        log=tmp/(label+"-allocator.log")
        saved=f.read_bytes()
        try:
            call(["python3",str(HERE/"inject.py"),str(f),str(HERE/"allocator-proof.rs")])
            call(cargo+["build","--locked","--offline","-p","extension-context"])
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
    assert len(a.splitlines())==7
    print("verified_exact_wire",len(a.splitlines()),len(a),digest(a),flush=True)
    assert len(old)==len(new)==7
    assert old[0][2]-new[0][2]>=2_000_000, (old[0],new[0])
    # Loopback connection bookkeeping can move by a few KiB. Exact resident
    # hits have no HTTP, and the realistic opened popup must shed megabytes.
    assert old[1]==new[1] and old[6]==new[6]
    assert abs(old[0][3]-new[0][3])<=8192
    assert abs(old[3][2]-new[3][2])<=8192  # failed refresh never replaces cache
    assert abs(sum(r[2] for r in old[:5])-sum(r[2] for r in new[:5]))<=8192
    print("verified_native_context_metrics",json.dumps([old,new]),flush=True)
    apply("--reverse")
    assert snapshot(work)==base
    print("Native wire, freshness and retained Context differential verified.")

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    for flag in ("baseline","overlay409","overlay411","overlay414","overlay417","overlay419","desktop420","work"):
        cli.add_argument("--"+flag,type=Path,required=True)
    cli.add_argument("--vendor",type=Path)
    cli.add_argument("--native",action="store_true")
    cli.add_argument("--min-free-mib",type=int,default=110)
    args=cli.parse_args()
    assert not args.native or args.vendor is not None
    pins=json.loads((HERE/"receipt.json").read_bytes())
    assert digest(args.baseline.read_bytes())==pins["input_archive"]["sha256"]
    assert [digest(p.read_bytes()) for p in (args.overlay409,args.overlay411,args.overlay414,args.overlay417,args.overlay419)]==[
        item["sha256"] for item in pins["verified_overlays"]]
    assert digest((HERE/"source.patch").read_bytes())==pins["patch_sha256"]
    desktop_patch=args.desktop420.read_bytes()
    selector=pins["m420_selector"]
    assert digest(desktop_patch)==selector["patch_sha256"]
    assert git_object("blob",desktop_patch).hex()==selector["remote_git_blob_sha1"]
    from_paths=[ln.removeprefix(b"--- a/").decode() for ln in desktop_patch.splitlines() if ln.startswith(b"--- a/")]
    to_paths=[ln.removeprefix(b"+++ b/").decode() for ln in desktop_patch.splitlines() if ln.startswith(b"+++ b/")]
    assert from_paths==to_paths==selector["source_paths"]
    with tempfile.TemporaryDirectory(prefix="context-popup-native-",dir=args.work.resolve(strict=True)) as td:
        verify(args,pins,Path(td))

if __name__=="__main__":
    main()
