#!/usr/bin/env python3
"""Stage native session-storage with source and offline lock checks; never build on import."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, tarfile, tomllib

HERE = Path(__file__).resolve().parent
SOURCE_FILES_DIGEST = "244be3e6a935fe37273628d4c29a3979b182a83f7ed69bb88b7b6d2953cf3baa"
PROOF_LOCK_DIGEST = "afe8a82478460c5b7be666666196f5a723c88b299794039a9ae2a6b2a262266c"
TOOL_PINS = {
    "cargo": "841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66",
    "rustc": "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6",
    "rustfmt": "56b31ad3ec8fe0277a2884a189e243b8f04e9b48e5fd22e547c1516c5f8fd34c",
}
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"
MANIFEST = '''[workspace]
resolver = "2"
members = ["storage/session-storage"]
default-members = ["storage/session-storage"]

[workspace.dependencies]
proteus-contracts = { path = "../Core/crates/proteus-contracts" }
proteus-session-semantics = { path = "../Core/crates/proteus-session-semantics" }

[profile.dev]
debug = "line-tables-only"
'''

def need(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()

def safe(name):
    p = Path(name)
    need(not p.is_absolute() and p.parts and ".." not in p.parts and p.as_posix() == name, f"unsafe path {name}")
    return p

def check_source(checkout, spec, destinations):
    entries = {safe(p): (mode, digest, size) for p, mode, digest, size in spec["blobs"]}
    need(len(entries) == len(spec["blobs"]), "duplicate source inventory path")
    actual = set()
    for root in map(safe, spec["roots"]):
        p = checkout/root
        need(p.is_dir() and not p.is_symlink(), f"source directory {p}")
        for child in p.rglob("*"):
            need(not child.is_symlink(), f"source symlink {child}")
            if child.is_file():
                actual.add(child.relative_to(checkout))
            else:
                need(child.is_dir(), f"nonregular source item {child}")
    need(actual == set(entries), "exact staged source inventory")
    for p, (mode, digest, size) in entries.items():
        source = checkout/p
        need(source.resolve().is_relative_to(checkout), f"escaping source path {source}")
        b = source.read_bytes()
        need(len(b) == size and git_blob(b) == digest and mode in ("100644", "100755"), f"pinned source bytes {p}")
        for d in destinations:
            target = d/p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b)
            target.chmod(0o755 if mode == "100755" else 0o644)
    lock = (checkout/"Cargo.lock").read_bytes()
    need(git_blob(lock) == spec["lock_git_blob"], "official lock blob")
    return lock

def vendorize(proof_lock, official_lock, archives, dest):
    reg = lambda lock: { (p["name"],p["version"]):(p["source"],p["checksum"])
                         for p in tomllib.loads(lock.decode())["package"] if "checksum" in p }
    expected, upstream = reg(proof_lock), reg(official_lock)
    need(len(expected) == 157, "exact native registry package resolution")
    dest.mkdir()
    for (n,v),(source,digest) in expected.items():
        name = f"{n}-{v}"
        need(upstream.get((n,v)) == (source,digest) and source == REGISTRY, f"upstream package pin {name}")
        root = dest/safe(name)
        root.mkdir()
        archive = next((d/(name+".crate") for d in archives if (d/(name+".crate")).is_file()), None)
        need(archive is not None and sha(archive.read_bytes()) == digest, f"official archive bytes {name}")
        files = {}
        with tarfile.open(archive, "r:gz") as t:
            for e in t:
                p = safe(e.name)
                need(p.parts[0] == name, f"archive prefix {e.name}")
                if e.isdir():
                    continue
                need(e.isfile() and len(p.parts) > 1, f"regular archive file {e.name}")
                relative = Path(*p.parts[1:])
                s = relative.as_posix()
                need(s not in files and s != ".cargo-checksum.json", f"duplicate archive file {e.name}")
                b = t.extractfile(e).read()
                target = root/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b)
                if e.mode & 0o100:
                    target.chmod(0o755)
                files[s] = sha(b)
        (root/".cargo-checksum.json").write_text(json.dumps({"package":digest,"files":files},sort_keys=True))

def stage_native_inputs(modules, core, work, tools, archives, packet=HERE):
    """Require fresh work path; copy exact three native crates, ready for overlays."""
    packet, modules, core, work, tools = map(lambda p:Path(p).resolve(),(packet,modules,core,work,tools))
    archives = [Path(p).resolve(strict=True) for p in archives]
    for binary, pinned in TOOL_PINS.items():
        need(sha((tools/binary).read_bytes()) == pinned, f"Rust 1.95.0 tool hash {binary}")
    inventory = (packet/"source-files.json").read_bytes()
    need(sha(inventory) == SOURCE_FILES_DIGEST, "exact source inventory")
    spec = json.loads(inventory)
    lock = (packet/"Cargo.lock").read_bytes()
    need(sha(lock) == PROOF_LOCK_DIGEST == spec["proof_lock_sha256"], "exact native Cargo.lock")
    work.mkdir(parents=True, exist_ok=False)
    native = work/"native"
    stock, candidate = native/"stock", native/"candidate"
    official = check_source(modules,spec["Modules"],[stock,candidate])
    check_source(core,spec["Core"],[native/"Core"])
    for arm in [stock,candidate]:
        (arm/"Cargo.toml").write_text(MANIFEST)
        (arm/"Cargo.lock").write_bytes(lock)
    vendorize(lock,official,archives,work/"vendor")
    for name in ("cargo-home","target","tmp"):
        (work/name).mkdir()
    return stock,candidate

def cargo(work, tools, side, *args, capture=False):
    work,tools = Path(work).resolve(),Path(tools).resolve()
    need(side in ("stock","candidate"), "known replay arm")
    home=work/"cargo-home"
    env={"PATH":str(tools)+":/usr/bin:/bin","HOME":str(home),"CARGO_HOME":str(home),
         "CARGO_TARGET_DIR":str(work/"target"),"RUSTC":str(tools/"rustc"),"LC_ALL":"C.UTF-8","TMPDIR":str(work/"tmp")}
    argv=[tools/"cargo","--offline","--locked","--config",'source.crates-io.replace-with="verified"',
          "--config","source.verified.directory="+json.dumps(str(work/"vendor")),*args]
    return subprocess.run(argv,cwd=work/"native"/side,env=env,check=True,
                          stdout=subprocess.PIPE if capture else None,text=True).stdout
