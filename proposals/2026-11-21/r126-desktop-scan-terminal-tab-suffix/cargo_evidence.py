"""Bind fresh warm native tabs and focused probe artifacts to their exact inputs."""
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
def artifact(name, manifest, source, test):
    obj, = (x for x in records if x.get("reason") == "compiler-artifact" and x["target"]["name"] == name
            and Path(x["manifest_path"]).resolve() == root / manifest and x["profile"]["test"] == test)
    assert obj["target"]["kind"] == obj["target"]["crate_types"] == ["lib"]
    assert Path(obj["target"]["src_path"]).resolve() == root / source
    assert obj["profile"]["opt_level"] == "0" and obj["fresh"] is False
    return obj

tabs = artifact("proteus_tabs", "crates/tabs/Cargo.toml", "crates/tabs/src/lib.rs", False)
rlib, = (Path(n).resolve(strict=True) for n in tabs["filenames"] if n.endswith(".rlib"))
assert rlib.parent == warm / "debug/deps"
rlib_before = sha(rlib)
results, statuses, errs = [], [], []
for name, manifest, source, total in [
    ("proteus_tabs", "crates/tabs/Cargo.toml", "crates/tabs/src/lib.rs", 72),
    ("desktop_terminal_suffix_probe", "Cargo.toml", "src/lib.rs", 4),
]:
    obj = artifact(name, manifest, source, True)
    exe = Path(obj["executable"]).resolve(strict=True)
    assert exe.parent == warm / "debug/deps" and re.fullmatch(name + "-[0-9a-f]+", exe.name)
    digest = sha(exe)
    run = subprocess.run([str(exe), "--test-threads=1", "--nocapture"], cwd=root, capture_output=True)
    out(name + ".stdout").write_bytes(run.stdout)
    out(name + ".stderr").write_bytes(run.stderr)
    if run.returncode:
        print(run.stdout.decode(errors="replace")[-9000:], run.stderr.decode(errors="replace")[-9000:])
        sys.exit(run.returncode)
    names = [line[5:-7] for line in run.stdout.decode().splitlines()
             if line.startswith("test ") and line.endswith(" ... ok")]
    assert len(names) == total and len(set(names)) == total
    statuses.append(f"{name}: {len(names)}/{total}")
    errs += run.stderr.split(b"\n")
    after = sha(exe)
    assert digest == after
    results.append({"manifest":manifest,"source":source,"test":True,"fresh":False,
                    "executable":exe.relative_to(warm).as_posix(),"sha256_before":digest,
                    "sha256_after":after,"tests":names,"profile":obj["profile"]})
assert errs.count(("ARM " + stamp).encode()) == 1
trace = [l for l in errs if l.startswith(b"TRACE ")]
work = [l for l in errs if l.startswith(b"WORK ")]
assert len(trace) == 11 and len(work) == 9, (len(trace), len(work))
out("trace-full").write_bytes(b"\n".join(trace) + b"\n")
summary = []
for line in trace:
    _, label, data = line.split(b" ", 2)
    json.loads(data)
    summary.append(b" ".join((label, str(len(data)).encode(), hashlib.sha256(data).hexdigest().encode())))
out("trace").write_bytes(b"\n".join(summary) + b"\n")
out("work").write_bytes(("ARM " + stamp + "\n").encode() + b"\n".join(work) + b"\n")
assert inputs(root) == bound and sha(rlib) == rlib_before
record = {"arm":stamp, "tests":results, "tabs_rlib_sha256":rlib_before, "inputs_sha256":bound,
          "patch_sha256":sha(Path(patch)), "trace_sha256":sha(out("trace")),
          "trace_full_sha256":sha(out("trace-full")), "work_sha256":sha(out("work")),
          "cargo":tool("cargo"), "rustc":tool("rustc")}
out("provenance").write_text(json.dumps(record, sort_keys=True) + "\n")
print(f"PASS fresh artifacts {stamp}, " + "; ".join(statuses) + "; 11 full byte records")
