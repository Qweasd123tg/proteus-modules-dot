"""Bind fresh warm artifacts to exact source; run focused native+fixture tests only."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs(src):
    return {x.relative_to(src).as_posix(): sha(x) for x in sorted(src.rglob("*")) if x.is_file()}
def tool(name):
    exe = Path(shutil.which(name)).resolve(strict=True)
    return {"sha256": sha(exe), "version": subprocess.check_output([exe, "--version"], text=True).strip()}

verb, root, prefix, *rest = sys.argv[1:]
root, prefix = Path(root).resolve(strict=True), Path(prefix).resolve()
def out(suffix): return Path(str(prefix) + "." + suffix)
if verb == "snapshot":
    out("inputs").write_text(json.dumps(inputs(root), sort_keys=True) + "\n")
    sys.exit()
assert verb == "run"
stamp, patch = rest
bound = json.loads(out("inputs").read_text())
assert bound == inputs(root)
records = [json.loads(l) for l in out("cargo-json").read_text().splitlines()]
assert [x["success"] for x in records if x.get("reason") == "build-finished"] == [True]
warm = Path(os.environ["CARGO_TARGET_DIR"]).resolve(strict=True)
name = "desktop_codex_live_delta_ids_probe"
sel, = (x for x in records if x.get("reason") == "compiler-artifact" and x["target"]["name"] == name
        and Path(x["manifest_path"]).resolve() == root / "Cargo.toml" and x["profile"]["test"])
assert sel["target"]["kind"] == ["lib"] and sel["target"]["crate_types"] == ["lib"]
assert Path(sel["target"]["src_path"]).resolve() == root / "src/lib.rs"
assert sel["profile"]["opt_level"] == "0" and sel["fresh"] is False
artifacts = {o["target"]["name"]: o for o in records if o.get("reason") == "compiler-artifact"
             and o["target"]["kind"] == ["lib"]}
serde = artifacts["serde_json"]
assert "preserve_order" in serde["features"] and "#serde_json@1.0.152" in serde["package_id"]
contracts = artifacts["proteus_contracts"]
assert "7cbc7206" in contracts["package_id"]
exe = Path(sel["executable"]).resolve(strict=True)
assert exe.parent == warm / "debug/deps" and re.fullmatch(name + "-[0-9a-f]+", exe.name)
before = sha(exe)

def tests(src, prefix):
    marker = r"#\[(?:::core::prelude::v1::)?test\]\s+fn (\w+)\("
    return sorted(prefix + n for n in re.findall(marker, (root / "src" / src).read_text()))

testsets = [("transcript::external::tests::", "transcript/external.rs", 6),
            ("transcript::reasoning_tests::", "transcript/reasoning_tests.rs", 7), ("proof::", "cases.rs", 4)]
names, errs = [], []
for test_filter, source, total in testsets:
    expected = tests(source, test_filter)
    assert len(expected) == total
    run = subprocess.run([str(exe), test_filter, "--test-threads=1", "--nocapture"], cwd=root, capture_output=True)
    out(source.split("/")[-1] + ".stdout").write_bytes(run.stdout)
    out(source.split("/")[-1] + ".stderr").write_bytes(run.stderr)
    if run.returncode:
        print(run.stdout.decode(errors="replace")[-7000:], run.stderr.decode(errors="replace")[-7000:])
        sys.exit(run.returncode)
    passed = [line[5:-7] for line in run.stdout.decode().splitlines()
              if line.startswith("test ") and line.endswith(" ... ok")]
    assert sorted(passed) == expected, passed
    names += sorted(passed)
    errs += run.stderr.split(b"\n")
assert errs.count(("ARM " + stamp).encode()) == 1
trace = [l for l in errs if l.startswith(b"TRACE ")]
work = [l for l in errs if l.startswith(b"WORK ")]
assert len(trace) == 4 and len(work) == 5, (len(trace), len(work))
out("trace-full").write_bytes(b"\n".join(trace) + b"\n")
summary = []
for line in trace:
    _, label, data = line.split(b" ", 2)
    json.loads(data)
    summary.append(b" ".join((label, str(len(data)).encode(), hashlib.sha256(data).hexdigest().encode())))
out("trace").write_bytes(b"\n".join(summary) + b"\n")
out("work").write_bytes(("ARM " + stamp + "\n").encode() + b"\n".join(work) + b"\n")
after = sha(exe)
assert before == after and inputs(root) == bound
record = {"arm": stamp, "manifest": "Cargo.toml", "source": "src/lib.rs", "test": True, "fresh": False,
          "executable": exe.relative_to(warm).as_posix(), "sha256_before": before, "sha256_after": after,
          "serde_json_features": serde["features"], "contracts": contracts["package_id"].split("#")[-1],
          "profile": sel["profile"], "tests": sorted(names),
          "inputs_sha256": bound, "patch_sha256": sha(Path(patch)), "trace_sha256": sha(out("trace")),
          "trace_full_sha256": sha(out("trace-full")), "work_sha256": sha(out("work")),
          "cargo": tool("cargo"), "rustc": tool("rustc")}
out("provenance").write_text(json.dumps(record, sort_keys=True) + "\n")
print(f"PASS fresh artifact {stamp}: 13/13 native transcript external/reasoning tests, 4/4 lifted fixture tests, 4 full byte snapshots")
