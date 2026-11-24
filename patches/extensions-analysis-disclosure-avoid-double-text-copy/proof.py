#!/usr/bin/env python3
"""Verify and reproduce the exact native R265 Analysis disclosure proof."""
import argparse
from concurrent.futures import ThreadPoolExecutor
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
TARGET = "packages/analysis/src/nodes.rs"
SDK = "sdk/src/ui.rs"
STOCK = "9e60315fde3e570a7b4b5de7b37dca818cb7b095"
CANDIDATE = "90e54c3d8a35819afe112ec865ef83b36ab55e96"
LOCK = "9b9aa368f874b87c91f367ea5e5eb432a86ef10b"


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
    require(git_blob((src / TARGET).read_bytes()) == STOCK, "stock Analysis helper")
    require(git_blob((src / "Cargo.lock").read_bytes()) == LOCK, "pinned native lock")
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


def suite_result(log, passed, filtered):
    output = log.read_text()
    groups = re.findall(
        r"^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; "
        r"(\d+) measured; (\d+) filtered out", output, re.M
    )
    require(groups == [(str(passed), "0", "0", "0", str(filtered))], f"unexpected test result: {log}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path, help="clean pinned Extensions workspace")
    parser.add_argument("--deps", required=True, type=Path, help="archives/ and vendor/ from the official lock")
    parser.add_argument("--toolchain", required=True, type=Path, help="Rust/Cargo/rustfmt 1.95.0 bin directory")
    parser.add_argument("--work", required=True, type=Path, help="writable scratch parent outside all inputs")
    parser.add_argument("--compose-rich-text", type=Path, help="optional exact Dot #570 source.patch")
    args = parser.parse_args()
    src, deps, bin_dir, work = [path.resolve(strict=True) for path in [
        args.src, args.deps, args.toolchain, args.work
    ]]
    require(not work.is_relative_to(src) and not work.is_relative_to(deps), "scratch must be outside source and dependencies")
    meta = json.loads((PACKET / "SOURCE-PROVENANCE.json").read_bytes())
    entries = verify_sources(meta, src)
    verify_deps(src, deps)
    patch = PACKET / "source.patch"
    rich_text = args.compose_rich_text.resolve(strict=True) if args.compose_rich_text else None
    compositions = ["stock", "candidate"] + (["composed"] if rich_text else [])
    if rich_text:
        provenance = meta["optional_dot_570"]
        require(sha(rich_text.read_bytes()) == provenance["patch_sha256"]
                and git_blob(rich_text.read_bytes()) == provenance["patch_blob"], "exact #570 patch identity")

    scratch = Path(tempfile.mkdtemp(prefix="r265-proof-", dir=work))
    print(f"Proof logs: {scratch}", flush=True)

    def trial(name):
        case = scratch / name
        case.mkdir()
        home = case / "cargo-home"
        home.mkdir()
        snapshots = case / "snapshots"
        snapshots.mkdir()
        ws = case / "workspace"
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
            "CARGO_TARGET_DIR": str(case / "target"),
            "CARGO_NET_OFFLINE": "true",
            "CARGO_BUILD_JOBS": "3",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CEILING_DIRECTORIES": str(case),
            "R265_SNAPSHOTS": str(snapshots),
        }
        env.pop("RUSTC_WRAPPER", None)
        env.pop("RUSTC_WORKSPACE_WRAPPER", None)
        env.pop("RUSTFLAGS", None)
        env.pop("CARGO_ENCODED_RUSTFLAGS", None)

        def run(argv, log=None):
            result = subprocess.run(
                argv, cwd=ws, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=300, text=True
            )
            if log:
                log.write_text(result.stdout)
            require(result.returncode == 0, f"{name}: {argv}: {log or result.stdout}")
            return result.stdout

        for binary in ("cargo", "rustc", "rustfmt"):
            reported = run([str(bin_dir / binary), "--version"])
            expected = {"cargo": "cargo 1.95.0 ", "rustc": "rustc 1.95.0 ", "rustfmt": "rustfmt 1.9.0-stable (59807616e1 "}[binary]
            require(expected in reported, f"unexpected {binary} version: {reported}")
        cargo = [
            str(bin_dir / "cargo"), "--config", 'source.crates-io.replace-with="verified-vendor"',
            "--config", 'source.verified-vendor.directory=' + json.dumps(str(deps / "vendor")),
            "test", "--locked", "--offline", "-p", "extension-analysis",
        ]
        if name != "stock":
            numstat = run(["git", "apply", "--numstat", str(patch)]).strip().splitlines()
            require(len(numstat) == 1 and numstat[0].split("\t", 2)[2] == TARGET, "only the Analysis helper path may change")
            run(["git", "apply", "--check", str(patch)])
            run(["git", "apply", str(patch)])
            require(git_blob((ws / TARGET).read_bytes()) == CANDIDATE, "expected candidate helper")
            run(["git", "apply", "-R", "--check", str(patch)])
            run(["git", "apply", "-R", str(patch)])
            require(git_blob((ws / TARGET).read_bytes()) == STOCK, "reverse must restore exact stock blob")
            run(["git", "apply", str(patch)])
        if name == "composed":
            run(["git", "apply", "--check", str(rich_text)])
            run(["git", "apply", str(rich_text)])
            run(["git", "apply", "-R", "--check", str(rich_text)])

        for rel, mode, expected, _ in entries:
            f = ws / rel
            if rel == TARGET and name != "stock":
                expected = CANDIDATE
            elif rel == SDK and name == "composed":
                expected = meta["optional_dot_570"]["sdk_after_blob"]
            data = os.readlink(f).encode() if mode == "120000" else f.read_bytes()
            require(git_blob(data) == expected, f"unexpected change in {name}: {rel}")
        fmt = [str(bin_dir / "rustfmt"), "--check", "--edition", "2024"]
        run(fmt + [TARGET])
        clean_log = case / "native.log"
        run(cargo, clean_log)
        suite_result(clean_log, 19, 0)
        require("Compiling extension-analysis" in clean_log.read_text() and str(case / "target") in clean_log.read_text(),
                f"{name}: package compile must run in its own target")
        mod = ws / TARGET
        stock_src = mod.with_name("r265_stock_nodes.rs")
        proof_src = mod.with_name("r265_disclosure_proof.rs")
        shutil.copyfile(src / TARGET, stock_src)
        shutil.copyfile(PACKET / "disclosure_proof.rs", proof_src)
        with mod.with_name("main.rs").open("a") as crate:
            crate.write("\n#[cfg(test)]\nmod r265_disclosure_proof;\n")
        run(fmt + [str(proof_src)])
        harness_args = ["--", "--test-threads=1", "--nocapture"]
        if name == "stock":
            harness_args.extend(["--skip", "optimized_helper_requests_match_controls"])
        proof_log = case / "proof.log"
        run(cargo + ["--release", "r265_disclosure_proof"] + harness_args, proof_log)
        suite_result(proof_log, 4 if name == "stock" else 5, 20 if name == "stock" else 19)
        require(git_blob((ws / "Cargo.lock").read_bytes()) == LOCK, f"{name}: unchanged lock after native builds")
        print(f"{name}: 19 original tests; {4 if name == 'stock' else 5} release verification tests passed.", flush=True)
        return snapshots

    with ThreadPoolExecutor(max_workers=len(compositions)) as pool:
        results = dict(zip(compositions, pool.map(trial, compositions)))
    for snapshot in ("turn.json", "tool.json"):
        base = (results["stock"] / snapshot).read_bytes()
        for name in compositions[1:]:
            require((results[name] / snapshot).read_bytes() == base, f"production caller bytes differ: {snapshot} {name}")
        print(f"{snapshot}: {len(base)} identical native bytes; SHA256 {sha(base)}.")
    for name in compositions[1:]:
        for line in (scratch / name / "proof.log").read_text().splitlines():
            if "requested bytes" in line:
                print(name + ": " + line)
    print("Exact application, reverse, formatting, original lock, native package, bytes and allocator proof passed.")


if __name__ == "__main__":
    main()
