#!/usr/bin/env python3
"""Verify a proof vendor tree against the actual Desktop Cargo.lock and official crate bytes.

Usage: python3 desktop_inputs.py UPSTREAM_CARGO_LOCK PROOF_CARGO_LOCK ARCHIVES VENDOR
This reads files only. A proof can share a larger vendor cache; only its locked registry
closure is accepted and verified. No network, unsafe extraction, or Cargo invocation.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tomllib

LOCK_BLOB = "c2f4e911288ce26efa47dfd0017c514c17ebc879"
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"

def require(ok, error):
    if not ok:
        raise ValueError(error)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def git_blob(b):
    return hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest()

def verify_vendor(upstream_lock, proof_lock, archives, vendor):
    up = upstream_lock.read_bytes()
    require(git_blob(up) == LOCK_BLOB, "upstream Desktop lock")
    official = {(p["name"], p["version"], p["source"]): p.get("checksum")
                for p in tomllib.loads(up.decode())["package"] if "source" in p}
    lock = tomllib.loads(proof_lock.read_text())["package"]
    # The proof may introduce local path packages; remote/git dependencies are not allowed.
    remote = [p for p in lock if "source" in p]
    require(len(remote) > 0, "expected registry packages in proof")
    checked = []
    for p in sorted(remote, key=lambda x:(x["name"],x["version"])):
        n, v, src = p["name"], p["version"], p["source"]
        key = n, v, src
        require(src == REGISTRY and p.get("checksum") and p["checksum"] == official.get(key),
                f"unrecognized upstream pin: {n} {v} {src}")
        pkg = f"{n}-{v}"
        require('/' not in pkg and '\\' not in pkg, f"unexpected package name {pkg}")
        archive = archives / (pkg + ".crate")
        root = vendor / pkg
        require(root.is_dir() and not root.is_symlink(), f"missing vendor package {pkg}")
        require(sha(archive.read_bytes()) == p["checksum"], f"archive identity {pkg}")
        expected = {}
        with tarfile.open(archive, "r:gz") as t:
            for m in t:
                path = PurePosixPath(m.name)
                require(path.parts and path.parts[0] == pkg and ".." not in path.parts, m.name)
                if m.isdir():
                    continue
                require(m.isfile() and len(path.parts) > 1, f"nonfile {m.name}")
                f = path.relative_to(pkg).as_posix()
                require(f not in expected and f != ".cargo-checksum.json", m.name)
                expected[f] = sha(t.extractfile(m).read())
        actual = {}
        for file in root.rglob("*"):
            require(not file.is_symlink(), f"symlink in vendor: {file}")
            if file.is_dir():
                continue
            require(file.is_file(), f"nonfile in vendor: {file}")
            f = file.relative_to(root).as_posix()
            if f != ".cargo-checksum.json":
                actual[f] = sha(file.read_bytes())
        require(actual == expected, f"vendored file inventory/content mismatch {pkg}")
        sums = json.loads((root/".cargo-checksum.json").read_text())
        require(sums == {"package":p["checksum"], "files":expected}, f"vendor manifest {pkg}")
        checked.append((n,v,p["checksum"],len(expected)))
    require(len({a[:2] for a in checked}) == len(checked), "duplicate registry entries")
    return {"desktop_lock_blob": LOCK_BLOB, "proof_lock_sha256":sha(proof_lock.read_bytes()),
            "archive_count":len(checked), "file_count":sum(x[3] for x in checked),
            "registry":REGISTRY, "packages":checked}

if __name__ == "__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ("upstream_lock","proof_lock","archives","vendor"):
        ap.add_argument(n, type=Path)
    print(json.dumps(verify_vendor(**vars(ap.parse_args())), indent=2))
