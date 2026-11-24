#!/usr/bin/env python3
"""Build paired source-bound JSONL exercises from pinned read-only inputs."""
import argparse, hashlib, json, os, re, shutil, subprocess
from pathlib import Path
from offline_deps import TOOL_PINS, verify_archives
from fixture_oracle import report as oracle_report

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / "SOURCE-PROVENANCE.json").read_text())


def run(*args, **kw):
    return subprocess.run(args, check=True, **kw)


def span(s, a, b):
    begin = s.index(a)
    return s[begin:s.index(b, begin + len(a))]


def decl(s, name):
    p = re.search(r"\b(?:struct|enum) " + name + r" \{", s).start()
    return s[s.rindex("#[derive(", 0, p):s.index("\n}", p) + 2] + "\n"


def replace(s, a, b):
    assert s.count(a) == 1, a
    return s.replace(a, b)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def emit(refs, work, src, fmt):
    pinned = {}
    for p in PINS["sources"]:
        raw = (refs / p["area"] / p["path"]).read_bytes()
        assert git_blob(raw) == p["sha"], (p["path"], "source pin")
        pinned[p["area"], p["path"]] = raw.decode()
    read = lambda repo, suffix: next(v for (r, p), v in pinned.items() if r == repo and p.endswith(suffix))
    changed = PINS["changed_path"]
    old = pinned["modules", changed]
    local = work / "patch-check"
    (local / changed).parent.mkdir(parents=True)
    (local / changed).write_text(old)
    patch = HERE / "source.patch"
    run("git", "-C", local, "apply", "--check", patch)
    run("git", "-C", local, "apply", patch)
    new = (local / changed).read_text()
    expected = replace(old, "atomic_write, bounded_read,", "atomic_write, bounded_file_eq,")
    expected = replace(expected, "bounded_read(&path, MAX_CHUNK)? == bytes", "bounded_file_eq(&path, bytes, MAX_CHUNK)?")
    assert new == expected and git_blob(new.encode()) == PINS["postimage"]
    run(fmt, "--check", "--edition", "2024", local / changed)
    run("git", "-C", local, "apply", "-R", "--check", patch)
    run("git", "-C", local, "apply", "-R", patch)
    assert (local / changed).read_text() == old

    ros = read("sdk", "/storage/journal.rs")
    msg = read("sdk", "/model_standard/content_part.rs")
    ids = read("sdk", "/domain/ids.rs")
    dto = "use serde::{Serialize, Deserialize};\nuse uuid::Uuid;\n"
    dto += "\n".join(line for line in ids.splitlines() if re.match(r"pub type (ExecutionId|RecordId|SessionId|ThreadId|TurnId|MessageId|PartId|CallId) = ", line)) + "\n"
    dto += span(ids, "#[derive(", "impl ExecutionId")
    dto += next(line for line in ros.splitlines() if line.startswith("pub const JOURNAL_SCHEMA_VERSION")) + "\n"
    dto += "".join(decl(ros, n) for n in ["HistoryMutationKind", "HistoryMutated", "JournalKind", "JournalRecord"])
    dto += "".join(decl(msg, n) for n in ["MessageRole", "MessagePhase", "CanonicalMessage", "PartProvenance", "PartScope", "CanonicalPart"])
    dto += span(ros, "    pub fn payload_value(&self)", "    pub fn from_kind_and_payload").join(["impl JournalEntry {\n", "}\n"])
    dto += (HERE / "model_adapter.rs").read_text()
    (src / "types.rs").write_text(dto)

    plain_io = read("modules", "/io.rs")
    codeio = plain_io[:plain_io.index("#[cfg(test)]")]
    codeio += span(plain_io, "/// Persist each newly created directory", "#[cfg(test)]")
    # Only inside the replay: temp filename token provider and deterministic after-open observation.
    codeio = replace(codeio, "uuid::Uuid::new_v4()", "crate::temp_uuid()")
    codeio = replace(codeio, "    Ok((file, metadata))", "    crate::observe_open(path, &file);\n    Ok((file, metadata))")
    (src / "io.rs").write_text(codeio)
    # A separate exercise lifts the exact loops and changes only the reader boundary.
    eq = span(plain_io, "pub(crate) fn bounded_file_eq", "/// Fill the caller's buffer")
    eq = replace(eq, "path: &Path", "reader: impl Read")
    eq = replace(eq, "open_regular(path)?.take", "reader.take")
    rd = span(plain_io, "fn read_bounded(file: File", "#[cfg(test)]")
    rd = replace(rd, "fn read_bounded(file: File", "pub(crate) fn read_bounded(file: impl Read")
    (src / "read_fault.rs").write_text("use anyhow::{Result, bail, ensure};\nuse std::io::Read;\n" + rd + eq)

    codec = read("modules", "/codec.rs")
    codec = replace(codec, "use proteus_contracts::domain::{ExecutionId, RecordId, SessionId, ThreadId, TurnId};\n", "")
    codec = replace(codec, span(codec, "pub(crate) fn canonicalize_entry", "pub(crate) fn encode"), "")
    codec = codec[:codec.index("#[cfg(test)]")]
    pl = read("modules", "/codec/payload.rs")
    pl = pl[:pl.index("#[cfg(test)]")]
    app = span(read("modules", "/backend/mod.rs"), "pub(crate) struct Append", "#[derive(Clone, PartialEq, Eq)]")
    backend = read("modules", "/backend/jsonl.rs")
    back = span(backend, "#[derive(Default)]", "impl JournalBackend for Jsonl")
    back += "impl Jsonl {\n" + span(backend, "    fn recover(", "    fn description_path(") + "}\n"
    back = back.replace("    fn recover(", "    pub(crate) fn recover(").replace("    fn append(", "    pub(crate) fn append(")
    use = """use crate::{io::{complete_jsonl_offset, restore_offset, sync_directory}, types::{JournalRecord,SessionId}};
use anyhow::{Context, Result, ensure};
use std::{fs::{File, OpenOptions}, io::Write, path::{Path, PathBuf}};
"""
    for side, b in [("stock", old), ("candidate", new)]:
        d = src / side
        (d / "codec").mkdir(parents=True)
        b = b[:b.index("#[cfg(test)]")]
        name = "bounded_read" if side == "stock" else "bounded_file_eq"
        b = replace(b, ", " + name + ",", ",")
        if side == "stock":
            b = replace(b, "bounded_read(&path, MAX_CHUNK)? == bytes", "bounded_read(&path, MAX_CHUNK, bytes)?")
        adapter = (
            "fn bounded_read(path:&Path, max:usize, bytes:&[u8])->Result<bool> { crate::stock_read(path,max,bytes) }\n"
            if side == "stock" else
            "fn bounded_file_eq(path:&Path, bytes:&[u8], max:usize)->Result<bool> { crate::candidate_eq(path,bytes,max) }\n"
        )
        (d / "blob_codec.rs").write_text(b + adapter)
        (d / "codec.rs").write_text(codec.replace("crate::blob_codec::", "super::blob_codec::"))
        (d / "codec" / "payload.rs").write_text(pl)
        (d / "mod.rs").write_text("mod blob_codec;\npub(crate) mod codec;\n" + use + app + back)
    shutil.copyfile(HERE / "exercise.rs", src / "main.rs")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--refs", type=Path, required=True)
    a.add_argument("--work", type=Path, required=True)
    a.add_argument("--toolchain-bin", type=Path, required=True)
    a.add_argument("--archives", type=Path, required=True, action="append")
    a.add_argument("--only", choices=["debug", "release"])
    p = a.parse_args()
    refs, work, bins = map(Path.resolve, [p.refs, p.work, p.toolchain_bin])
    for binary, expect in TOOL_PINS.items():
        assert hashlib.sha256((bins / binary).read_bytes()).hexdigest() == expect, binary
    work.mkdir(parents=True, exist_ok=False)
    src = work / "src"
    src.mkdir()
    emit(refs, work, src, bins / "rustfmt")
    vendor = work / "vendor"
    verify_archives(refs / "modules/Cargo.lock", refs / "sdk/Cargo.lock", HERE / "Cargo.lock",
                    [p.resolve() for p in p.archives], vendor)
    for name in ["Cargo.toml", "Cargo.lock"]:
        shutil.copyfile(HERE / name, work / name)
    cargo_home = work / "cargo-home"
    cargo_home.mkdir()
    (cargo_home / "config.toml").write_text("[source.crates-io]\nreplace-with = 'audited'\n[source.audited]\ndirectory = " + json.dumps(str(vendor)) + "\n")
    env = os.environ | {"CARGO_HOME": str(cargo_home), "RUSTC": str(bins / "rustc"),
                        "PATH": str(bins) + os.pathsep + os.environ["PATH"]}
    reports = {}
    oracle = oracle_report()
    for prof in ([p.only] if p.only else ["debug", "release"]):
        for layout in ["default", "preserve_order"]:
            args = [bins / "cargo", "run", "--offline", "--locked", "--quiet"]
            if prof == "release":
                args += ["--release"]
            if layout == "preserve_order":
                args += ["--features", layout]
            fdir = work / (prof + "-" + layout)
            fdir.mkdir()
            out = run(*args, "--", fdir, cwd=work, env=env, stdout=subprocess.PIPE).stdout
            result = json.loads(out)
            branch = result["real_append_cases"]["equal"]["candidate"]
            assert [branch["first_manifest_sha256"], branch["manifest_sha256"]] == oracle[layout]["manifest_sha256"]
            reports[prof + "-" + layout] = result
    reports_out = {"postimage": PINS["postimage"], "oracle": oracle, "reports": reports}
    (work / "verification.json").write_text(json.dumps(reports_out, sort_keys=True, indent=2) + "\n")
    print(json.dumps(reports_out, sort_keys=True))


if __name__ == "__main__":
    main()
