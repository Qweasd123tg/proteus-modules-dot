#!/usr/bin/env python3
"""Verify and expand the R271 offline dependency closure against both upstream locks."""
import hashlib
import json
import tarfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES_LOCK_BLOB = "ae7035fc5900b0afc480e55d2408c8234c88dd17"
CORE_LOCK_BLOB = "a9dbb28155a2d48753591f1a4391d9863d42314b"
TOOL_PINS = {
    "cargo": "841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66",
    "rustc": "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6",
    "rustfmt": "56b31ad3ec8fe0277a2884a189e243b8f04e9b48e5fd22e547c1516c5f8fd34c",
}
def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def identity(path):
    data = path.read_bytes()
    git_blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    return {"bytes": len(data), "sha256": sha(data), "git_blob": git_blob}

def verify_archives(modules_lock, core_lock, proof_lock, dirs, dest):
    need(identity(modules_lock)["git_blob"] == MODULES_LOCK_BLOB, "Modules published lock")
    need(identity(core_lock)["git_blob"] == CORE_LOCK_BLOB, "Core dependency lock")
    def index(p):
        return {(x["name"], x["version"]):x for x in tomllib.loads(p.read_text())["package"] if "checksum" in x}
    original = index(modules_lock)
    locked_core = index(core_lock)
    dest.mkdir()
    packages = [p for p in tomllib.loads(proof_lock.read_text())["package"] if "checksum" in p]
    need(len(packages) == 36, "exact proof archive closure")
    for pkg in packages:
        key = pkg["name"], pkg["version"]
        name = "-".join(key)
        archive = next((p/(name+".crate") for p in dirs if (p/(name+".crate")).is_file()), None)
        for upstream,repo in ((original, "Modules"), (locked_core, "Core")):
            pinned = upstream.get(key, {})
            need(pinned.get("source") == pkg["source"] and pinned.get("checksum") == pkg["checksum"],
                 f"official {repo} package pin {name}")
        need(archive and pkg["checksum"] == sha(archive.read_bytes()), f"official archive {name}")
        need(pkg["source"] == "registry+https://github.com/rust-lang/crates.io-index", f"registry identity {name}")
        root = dest/name
        root.mkdir()
        sums = {}
        with tarfile.open(archive, "r:gz") as tar:
            for entry in tar:
                full = Path(entry.name)
                need(not full.is_absolute() and full.parts[0] == name and ".." not in full.parts, f"safe archive path for {name}")
                if entry.isdir():
                    continue
                need(entry.isfile() and len(full.parts)>1, f"regular package file {name}")
                rel = Path(*full.parts[1:]); x = rel.as_posix()
                need(x not in sums and x != ".cargo-checksum.json", f"unique file {name}/{x}")
                p = root/rel; p.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(entry).read()
                p.write_bytes(data)
                if entry.mode & 0o100:
                    p.chmod(0o755)
                sums[x] = sha(data)
        (root/".cargo-checksum.json").write_text(json.dumps({"package": pkg["checksum"], "files": sums}, sort_keys=True))


