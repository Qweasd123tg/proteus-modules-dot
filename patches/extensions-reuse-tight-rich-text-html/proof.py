#!/usr/bin/env python3
"""Offline native Extensions SDK/Markdown rich_text proof at the exact Git pin."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

PACKET = Path(__file__).resolve().parent
UI = "sdk/src/ui.rs"
UI_STOCK = "2587517432bf0d6d62d919d5df888b0669498e05"
UI_CANDIDATE = "48a6c21016e2fa689f12a0b249d3c49051df0156"
LOCK_STOCK = "9b9aa368f874b87c91f367ea5e5eb432a86ef10b"
MERMAID_TEST = "different_sessions_share_one_worker_and_last_close_and_eof_reap_it"


def require(ok, label):
    if not ok:
        raise ValueError(label)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def verify_sources(meta, src):
    entries = meta["native_input_blobs"]
    require(len(entries) == len({row[0] for row in entries}) == 151, "native inventory count")
    for rel, mode, digest, length in entries:
        f = src / rel
        require(f.resolve(strict=True).is_relative_to(src), f"source outside checkout: {rel}")
        require(f.is_symlink() == (mode == "120000"), f"source Git mode: {rel}")
        if f.is_symlink():
            data = os.readlink(f).encode()
        else:
            require(f.is_file() and f.stat().st_mode & 0o111 == 0, f"source mode: {rel}")
            data = f.read_bytes()
        require(len(data) == length and git_blob(data) == digest, f"source Git blob: {rel}")
    require(git_blob((src / UI).read_bytes()) == UI_STOCK, "stock UI")
    require(git_blob((src / "Cargo.lock").read_bytes()) == LOCK_STOCK, "pinned native lock")
    return entries


def verify_deps(src, deps):
    lock = tomllib.loads((src / "Cargo.lock").read_text())["package"]
    registry = [p for p in lock if p.get("source") == "registry+https://github.com/rust-lang/crates.io-index"]
    require(len(registry) == 27, "pinned registry closure")
    files = 0
    expected_dirs = {f"{pkg['name']}-{pkg['version']}" for pkg in registry}
    vendor = deps / "vendor"
    require({f.name for f in vendor.iterdir()} == expected_dirs, "vendor package directory set")
    for pkg in registry:
        name = pkg["name"] + "-" + pkg["version"]
        archive = deps / "archives" / (name + ".crate")
        root = deps / "vendor" / name
        require(root.is_dir() and not root.is_symlink(), f"vendor root {name}")
        checksum_file = root / ".cargo-checksum.json"
        require(checksum_file.is_file() and not checksum_file.is_symlink(), f"vendor manifest {name}")
        sums = json.loads(checksum_file.read_bytes())
        require(sha(archive.read_bytes()) == sums["package"] == pkg["checksum"], f"archive {name}")
        contents = {}
        with tarfile.open(archive) as tar:
            for member in tar:
                if member.isdir():
                    continue
                prefix = name + "/"
                require(member.isfile() and member.name.startswith(prefix), f"archive path: {member.name}")
                rel = member.name.removeprefix(prefix)
                require(rel not in contents, f"duplicate archive path: {rel}")
                contents[rel] = sha(tar.extractfile(member).read())
        require(contents == sums["files"], f"archive member set: {name}")
        observed = set()
        for path in root.rglob("*"):
            require(not path.is_symlink(), f"unexpected vendor symlink: {path}")
            if not path.is_dir() and path != checksum_file:
                require(path.is_file(), f"unexpected vendor path: {path}")
                observed.add(path.relative_to(root).as_posix())
        require(observed == set(contents), f"vendor member set: {name}")
        for rel, digest in contents.items():
            f = root / rel
            require(f.resolve(strict=True).is_relative_to(root.resolve()), f"vendor path: {f}")
            require(not f.is_symlink() and sha(f.read_bytes()) == digest, f"vendor payload: {f}")
        files += len(contents)
    require(files == 1241, "vendor file count")
    print(f"Verified {len(registry)} official lock archives and all {files} vendor files.", flush=True)


def full_result(text, code):
    counts = [
        tuple(map(int, items))
        for items in re.findall(r"^test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed", text, re.M)
    ]
    require(len(counts) == 20, f"workspace result groups: {counts}")
    passed, failed = (sum(values) for values in zip(*counts))
    if code:
        t = f"test {MERMAID_TEST} ... FAILED"
        errors = [line for line in text.splitlines() if line.startswith("error:")]
        proc_children = Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children")
        require((passed, failed) == (343, 1) and t in text and "packages/mermaid-render/tests/wire.rs:155:5" in text
                and len(errors) == 2 and not proc_children.exists(), "unexpected workspace failure (see log)")
    else:
        require((passed, failed) == (344, 0), "workspace test count")
    return passed, failed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", required=True, type=Path, help="clean pinned checkout or verified workspace inputs")
    p.add_argument("--deps", required=True, type=Path, help="verified archives/ + vendor/ Cargo directory source")
    p.add_argument("--toolchain", required=True, type=Path, help="Rust 1.95 toolchain bin directory")
    p.add_argument("--work", required=True, type=Path, help="existing writable scratch parent, outside source")
    a = p.parse_args()
    src, deps, bin_dir, work = (path.resolve() for path in (a.src, a.deps, a.toolchain, a.work))
    meta = json.loads((PACKET / "SOURCE-PROVENANCE.json").read_text())
    entries = verify_sources(meta, src)
    require(not work.is_relative_to(src), "working directory cannot be inside stock sources")
    verify_deps(src, deps)
    logs = Path(tempfile.mkdtemp(prefix="r261-native-", dir=work))
    print(f"Proof logs: {logs}", flush=True)
    home = logs / "cargo-home"
    home.mkdir()
    ws = logs / "workspace"
    ws.mkdir()
    for rel, mode, _, _ in entries:
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "120000":
            target.symlink_to(os.readlink(src / rel))
        else:
            shutil.copyfile(src / rel, target)
    env = os.environ | {
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "RUSTC": str(bin_dir / "rustc"),
        "CARGO_HOME": str(home),
        "CARGO_TARGET_DIR": str(logs / "target"),
        "CARGO_NET_OFFLINE": "true",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CEILING_DIRECTORIES": str(logs),
    }

    def run(args, log=None, timeout=300):
        if log is None:
            return subprocess.run(args, cwd=ws, env=env, timeout=timeout, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode()
        file = logs / (log + ".log")
        with file.open("wb") as f:
            result = subprocess.run(args, cwd=ws, env=env, timeout=timeout, stdout=f, stderr=subprocess.STDOUT)
        return file.read_text(errors="replace"), result.returncode

    require(run([bin_dir / "rustc", "--version"]).startswith("rustc 1.95.0 "), "Rust 1.95.0")
    require(run([bin_dir / "cargo", "--version"]).startswith("cargo 1.95.0 "), "Cargo 1.95.0")
    cargo = [
        bin_dir / "cargo", "--config", 'source.crates-io.replace-with="r261-verified"',
        "--config", "source.r261-verified.directory=" + json.dumps(str(deps / "vendor")),
        "test", "--offline", "--locked", "-j", "4",
    ]
    base, basecode = run(cargo + ["--workspace", "--no-fail-fast"], "stock-workspace")
    base_result = full_result(base, basecode)
    print(f"Stock native workspace (passed, failed): {base_result}", flush=True)

    patch = PACKET / "source.patch"
    patch_body = patch.read_bytes()
    require(patch_body.count(b"diff --git ") == 1 and
            patch_body.startswith(b"diff --git a/sdk/src/ui.rs b/sdk/src/ui.rs\n"), "scope of production patch")
    require(sha(patch_body) == meta["source_patch_sha256"], "pinned patch")
    stock_ui = (ws / UI).read_bytes()
    lock = (ws / "Cargo.lock").read_bytes()
    before, after = stock_ui.split(b"pub fn rich_text(", 1)
    _, suffix = after.split(b"\n}\n", 1)

    def apply(*flags):
        run(["git", "apply", "--whitespace=error", *flags, patch])

    apply("--check")
    apply()
    v = (ws / UI).read_bytes()
    require(v.startswith(before + b"pub fn rich_text(") and v.endswith(b"\n}\n" + suffix), "only rich_text changed")
    require(git_blob(v) == UI_CANDIDATE, "candidate UI")
    run([bin_dir / "rustfmt", "--edition", "2024", "--check", UI])
    apply("-R", "--check")
    apply("-R")
    require((ws / UI).read_bytes() == stock_ui, "byte-exact patch reversal")
    apply()
    result, code = run(cargo + ["--workspace", "--no-fail-fast"], "candidate-workspace")
    candidate_result = full_result(result, code)
    require(candidate_result == base_result, "stock and candidate native results disagree")
    print(f"Candidate native workspace (passed, failed): {candidate_result}", flush=True)

    support = ws / "sdk/tests/support"
    support.mkdir(parents=True, exist_ok=True)
    (support / "r261_stock_ui.rs").write_bytes(stock_ui)
    shutil.copyfile(PACKET / "rich_text_proof.rs", ws / "sdk/tests/r261_rich_text.rs")
    shutil.copyfile(PACKET / "markdown_proof.rs", ws / "packages/markdown-render/tests/r261_math_free.rs")
    for name, args, marker in [
        ("rich-proof", ["--release", "-p", "proteus-extension", "--test", "r261_rich_text",
                        "--", "--test-threads=1", "--nocapture"], "10 passed; 0 failed"),
        ("markdown-proof", ["-p", "extension-markdown-render", "--test", "r261_math_free",
                            "--", "--nocapture"], "13 passed; 0 failed"),
    ]:
        text, code = run(cargo + args, name)
        require(not code and marker in text, f"{name}: see {logs}")
        for line in text.splitlines():
            if "len=" in line or "math-free native" in line or line.startswith("test result:"):
                print(line)
    require((ws / "Cargo.lock").read_bytes() == lock and git_blob(lock) == LOCK_STOCK, "unchanged native lock")


if __name__ == "__main__":
    main()
