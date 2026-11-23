#!/usr/bin/env python3
"""Rebuild the exact Core cache-tail lifetime experiment with official pinned archives."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

from lift import INPUTS, VIEW, generate

HERE = Path(__file__).resolve().parent


def check(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ident(path):
    d = path.read_bytes()
    return dict(bytes=len(d), sha256=sha(d),
                git_blob=hashlib.sha1(f"blob {len(d)}\0".encode()+d).hexdigest())


def vendorize(repo_lock, proof_lock, archive_paths, dst):
    pin = {(p["name"], p["version"]):(p["source"], p["checksum"])
           for p in tomllib.loads(repo_lock)["package"] if "checksum" in p}
    dst.mkdir()
    for p in tomllib.loads(proof_lock)["package"]:
        if "checksum" not in p:
            continue
        key = p["name"], p["version"]
        name = "-".join(key)
        file = next((root/(name+".crate") for root in archive_paths
                     if (root/(name+".crate")).is_file()), None)
        check(file and p["source"] == "registry+https://github.com/rust-lang/crates.io-index"
              and pin.get(key) == (p["source"], p["checksum"])
              and sha(file.read_bytes()) == p["checksum"], f"pinned official archive {name}")
        top = dst/name
        top.mkdir()
        sums = {}
        with tarfile.open(file, "r:gz") as tar:
            for entry in tar:
                rel = Path(entry.name)
                check(not rel.is_absolute() and rel.parts and rel.parts[0] == name
                      and ".." not in rel.parts, f"invalid archive path: {name}")
                if entry.isdir():
                    continue
                check(entry.isfile() and len(rel.parts) > 1, f"invalid package file: {name}")
                path = Path(*rel.parts[1:])
                check(path.as_posix() not in sums and path.as_posix() != ".cargo-checksum.json",
                      f"duplicate or reserved path: {name}")
                b = tar.extractfile(entry).read()
                out = top/path
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b)
                if entry.mode & 0o100:
                    out.chmod(0o755)
                sums[path.as_posix()] = sha(b)
        (top/".cargo-checksum.json").write_text(json.dumps(dict(package=p["checksum"],files=sums),sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--work",type=Path,required=True)
    parser.add_argument("--archives",type=Path,action="append",required=True)
    parser.add_argument("--toolchain-bin",type=Path,required=True)
    args = parser.parse_args()
    meta = json.loads((HERE/"SOURCE-PROVENANCE.json").read_text())
    orig = args.source.resolve(strict=True)
    bin = args.toolchain_bin.resolve(strict=True)
    check(set(meta["inputs"]) == set(INPUTS),"exact source file list")
    for path,pin in meta["inputs"].items():
        check(ident(orig/path) == pin,"original source pin: "+path)
    for path,pin in meta["packet_inputs"].items():
        check(ident(HERE/path) == pin,"packet input: "+path)
    for binary,pin in meta["toolchain"].items():
        check(sha((bin/binary).read_bytes()) == pin,"toolchain pin: "+binary)
    args.work.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="r263-verify-",dir=args.work.resolve()) as item:
        root = Path(item)
        env = dict(HOME=item,TMPDIR=item,LC_ALL="C",PATH=str(bin)+":/usr/bin:/bin",
                   RUSTC=str(bin/"rustc"),CARGO_HOME=str(root/"cargo-home"),
                   CARGO_TARGET_DIR=str(root/"target"),GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL="/dev/null",GIT_CEILING_DIRECTORIES=item)
        def run(cmd,cwd=root,capture=False):
            return subprocess.run(cmd,check=True,cwd=cwd,env=env,text=True,timeout=300,
                                  stdout=subprocess.PIPE if capture else None).stdout
        changed = root/"changed"
        view = changed/VIEW
        view.parent.mkdir(parents=True)
        shutil.copyfile(orig/VIEW,view)
        git = ["/usr/bin/git","apply","--whitespace=error-all"]
        patch = HERE/"source.patch"
        stat = run(git+["--numstat",patch],changed,True)
        check(stat.splitlines()==[f"6\t1\t{VIEW}"],"single expected production file and hunk totals")
        for flags in ([],["-R"],[]):
            run(git+["--check",*flags,patch],changed)
            run(git+flags+[patch],changed)
            check(ident(view)==(meta["inputs"][VIEW] if flags else meta["postimage"]),"apply or reverse byte identity")
        run([bin/"rustfmt","--check","--edition","2024","--config","skip_children=true",view])
        run([bin/"rustfmt","--check","--edition","2024",HERE/"exercise.rs"])
        vendorize((orig/"Cargo.lock").read_text(),meta["proof_lock"],args.archives,root/"vendor")
        crate = root/"crate"
        generate(orig,changed,crate/"src")
        (crate/"Cargo.toml").write_text(meta["proof_manifest"])
        (crate/"Cargo.lock").write_text(meta["proof_lock"])
        cfg = ["--config",'source.crates-io.replace-with="proof"',"--config",'source.proof.directory='+json.dumps(str(root/"vendor"))]
        for order in (False,True):
            for mode in ("debug","release"):
                extra = (["--release"] if mode=="release" else []) + (["--features","preserve_order"] if order else [])
                run([bin/"cargo","build","--locked","--offline",*cfg,*extra],crate)
                binary = root/"target"/mode/"r263-cache-tail-proof"
                out = run([binary],capture=True)
                key = ("preserve" if order else "default")+"/"+mode
                print(key+"\n"+out,flush=True,end="")
                check(out.splitlines()==meta["receipts"][key],"exact semantic and lifetime receipt: "+key)
        print("PASS: exact forward/reverse replay, official locked dependencies; projection bodies, ordered adapter calls and typed liveness in four arms.")


if __name__ == "__main__":
    main()
