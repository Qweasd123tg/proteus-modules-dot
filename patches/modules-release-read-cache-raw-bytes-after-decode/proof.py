#!/usr/bin/env python3
"""Replay only pinned ReadCache slices through real files, Serde and Ring."""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
from offline_deps import TOOL_PINS, verify_archives

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / "SOURCE-PROVENANCE.json").read_text())


def run(*args, **kw):
    return subprocess.run(args, check=True, **kw)


def span(s, a, b):
    start = s.index(a)
    return s[start:s.index(b, start + len(a))]


def decl(s, n):
    p = s.index("pub struct " + n + " {")
    return s[s.rindex("#[derive(", 0, p):s.index("\n}", p) + 2] + "\n"


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def emit_tree(refs, work, src):
    pinned = {}
    for p in PINS["sources"]:
        raw = (refs / p["area"] / p["path"]).read_bytes()
        assert git_blob(raw) == p["sha"], (p["path"], "source blob mismatch")
        pinned[p["area"], p["path"]] = raw.decode()
    product = PINS["changed_path"]
    patch = HERE / "source.patch"
    exact = work / "exact"
    (exact / product).parent.mkdir(parents=True)
    old = pinned["modules", product]
    (exact / product).write_text(old)
    run("git", "-C", exact, "apply", "--check", patch)
    run("git", "-C", exact, "apply", patch)
    new = (exact / product).read_text()
    assert new == old.replace("    if cache.source.session != session\n",
                              "    drop(bytes);\n    if cache.source.session != session\n")
    assert git_blob(new.encode()) == PINS["postimage"]
    candidate_full = work / "candidate-cache.rs"
    candidate_full.write_text(new)
    run("git", "-C", exact, "apply", "-R", "--check", patch)
    run("git", "-C", exact, "apply", "-R", patch)
    assert (exact / product).read_text() == old

    read = lambda repo, suffix: next(v for (r, p), v in pinned.items() if r == repo and p.endswith(suffix))
    assert "=> cache::read_cache(session, key, source)," in read("modules", "/service.rs")
    core = read("core", "/view/cache.rs")
    assert 'update_tools(store, source, &mut tools, &model.transcript)?;' in core
    assert 'write_content(store, source, &AppToolState::from(tool))?' in core
    assert 'let key = format!("display-data-{digest}")' in core
    for name, cache in [("stock", old), ("candidate", new)]:
        fragment = span(cache, "const CACHE_ENVELOPE_ALLOWANCE:", "impl State {")
        adapter = """
pub(super) fn envelope(source: &StorageSnapshot, value: &Value) -> Vec<u8> {
    serde_json::to_vec(&Cache { source, value }).unwrap()
}
pub(super) fn file_path(dir: &Path, key: &str) -> PathBuf { path(dir, key) }
"""
        (src / (name + ".rs")).write_text("use super::*;\n" + fragment + adapter)
    io = read("modules", "/io.rs")
    io_slice = span(io, "pub(crate) fn sha256_hex(", "pub(crate) fn sync_directory(")
    io_slice += span(io, "fn open_regular_with_metadata(", "/// Compare an existing object")
    io_slice += span(io, "pub(crate) fn bounded_read_with_size_hint(", "#[cfg(test)]")
    io_slice = io_slice.replace("pub(crate) fn bounded_read_with_size_hint(", "fn bounded_exact(")
    adapter = """
pub(crate) fn bounded_read_with_size_hint(path: &Path, maximum: usize, hint: usize) -> Result<Vec<u8>> {
    crate::event(b'R');
    let bytes = bounded_exact(path, maximum, hint)?;
    crate::watch(&bytes);
    Ok(bytes)
}
"""
    (src / "io.rs").write_text("use anyhow::{Result, bail, ensure};\nuse ring::digest::{SHA256, digest};\nuse std::{fs::File, io::Read, path::Path};\n" + io_slice + adapter)
    contract = read("sdk", "/session_storage.rs")
    dto = "use super::*;\n" + next(l for l in contract.splitlines() if l.startswith("pub const SESSION_STORAGE_MAX_CACHE_BYTES")) + "\n"
    for name in ["SessionLocator", "StorageRevision", "StorageSnapshot", "StorageMetadataDocument"]:
        dto += decl(contract, name)
    response = span(contract, 'pub enum SessionStorageResponse {', '    Session {')
    dto += '#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]\n#[serde(tag = "result", rename_all = "snake_case", deny_unknown_fields)]\n' + response
    dto += span(contract, '    Metadata {\n', '    CacheWritten {\n') + "}\n"
    dto += decl(read("core", "/transcript.rs"), "AppToolState")
    pack = read("core", "/packed.rs")
    packed = span(pack, "#[derive(Serialize, Deserialize)]", "fn pack")
    packed = packed.replace("pub(in crate::core::session_store::remote::view)", "pub(super)")
    for field in ["format", "history", "turns", "exchanges", "messages", "parts", "calls"]:
        packed = packed.replace("    " + field + ":", "    pub(super) " + field + ":")
    dto += packed
    (src / "model.rs").write_text(dto)
    (src / "value_hash.rs").write_text(read("sdk", "/value_hash.rs"))
    shutil.copyfile(HERE / "exercise.rs", src / "main.rs")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--refs", type=Path, required=True)
    a.add_argument("--work", type=Path, required=True)
    a.add_argument("--toolchain-bin", type=Path, required=True)
    a.add_argument("--archives", type=Path, required=True, action="append")
    a.add_argument("--only", choices=["debug", "release"])
    p = a.parse_args()
    refs, work, tools = map(Path.resolve, [p.refs, p.work, p.toolchain_bin])
    for binary, expect in TOOL_PINS.items():
        assert hashlib.sha256((tools / binary).read_bytes()).hexdigest() == expect, binary
    work.mkdir(parents=True, exist_ok=False)
    src = work / "src"
    src.mkdir()
    emit_tree(refs, work, src)
    run(tools / "rustfmt", "--check", "--edition", "2024", "--config", "skip_children=true", work / "candidate-cache.rs")
    vendor = work / "vendor"
    verify_archives(refs / "modules/Cargo.lock", refs / "sdk/Cargo.lock", HERE / "Cargo.lock",
                    [p.resolve() for p in p.archives], vendor)
    shutil.copyfile(HERE / "Cargo.toml", work / "Cargo.toml")
    shutil.copyfile(HERE / "Cargo.lock", work / "Cargo.lock")
    cargo_home = work / "cargo-home"
    cargo_home.mkdir()
    (cargo_home / "config.toml").write_text("[source.crates-io]\nreplace-with = 'audited'\n[source.audited]\ndirectory = " + json.dumps(str(vendor)) + "\n")
    env = os.environ | {"CARGO_HOME": str(cargo_home), "RUSTC": str(tools / "rustc"),
                        "PATH": str(tools) + os.pathsep + os.environ["PATH"]}
    reports = {}
    for prof in ([p.only] if p.only else ["debug", "release"]):
        for layout in ["default", "preserve_order"]:
            args = [tools / "cargo", "run", "--offline", "--locked", "--quiet"]
            if prof == "release":
                args += ["--release"]
            if layout == "preserve_order":
                args += ["--features", layout]
            fdir = work / (prof + "-" + layout)
            fdir.mkdir()
            out = run(*args, "--", fdir, cwd=work, env=env, stdout=subprocess.PIPE).stdout
            reports[prof + "-" + layout] = json.loads(out)
    assert reports
    for prof in ([p.only] if p.only else ["debug", "release"]):
        vanilla = reports[prof + "-default"]["large-typed-tool"]
        ordered = reports[prof + "-preserve_order"]["large-typed-tool"]
        assert vanilla["wire_sha256"] != ordered["wire_sha256"], "both map layouts must be distinct"
    result = {"postimage": PINS["postimage"],
              "scope": "exact source lift, real bounded filesystem IO and locked SDK Serde/Ring; injected locator",
              "reports": reports}
    (work / "verification.json").write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({k: {"cases": len(v), "large": v["large-typed-tool"]} for k,v in reports.items()}, indent=2))


if __name__ == "__main__":
    main()
