"""Admit only the exact fresh full tool-display test executable."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inputs(src):
    return {x.relative_to(src).as_posix(): sha(x) for x in sorted(src.rglob("*")) if x.is_file()}

def tool(name):
    exe = Path(shutil.which(name)).resolve(strict=True)
    return {"sha256": sha(exe), "version": subprocess.check_output([exe,"--version"],text=True).strip()}

verb, root, prefix, *rest = sys.argv[1:]
root, prefix = Path(root).resolve(strict=True), Path(prefix).resolve()

def out(suffix):
    return Path(f"{prefix}.{suffix}")

if verb == "snapshot":
    out("inputs").write_text(json.dumps(inputs(root), sort_keys=True) + "\n")
    sys.exit()
assert verb == "run"
stamp, patch = rest
bound = json.loads(out("inputs").read_text())
assert bound == inputs(root)
records = [json.loads(l) for l in out("cargo-json").read_text().splitlines()]
assert [x["success"] for x in records if x.get("reason") == "build-finished"] == [True]
name = "desktop_tool_display_probe"
selected, = (a for a in records if a.get("reason") == "compiler-artifact" and
             a["target"]["name"] == name and a["target"]["kind"] == ["lib"] and a["profile"]["test"])
assert Path(selected["manifest_path"]).resolve() == root / "Cargo.toml"
assert Path(selected["target"]["src_path"]).resolve() == root / "src/lib.rs"
assert selected["fresh"] is False and selected["profile"]["opt_level"] == "0"
exe = Path(selected["executable"]).resolve(strict=True)
warm = Path(os.environ["CARGO_TARGET_DIR"]).resolve(strict=True)
assert exe.parent == warm / "debug/deps" and re.fullmatch(name + "-[0-9a-f]+", exe.name)
serde, = (o for o in records if o.get("reason") == "compiler-artifact" and o["target"]["name"] == "serde_json" and o["target"]["kind"] == ["lib"])
assert ("preserve_order" in serde["features"]) == stamp.endswith("/ordered")
assert "float_roundtrip" in serde["features"]
before = sha(exe)
with out("stdout").open("wb") as stdout, out("stderr").open("wb") as stderr:
    run = subprocess.run([str(exe), "--test-threads=1", "--nocapture"], cwd=root, stdout=stdout, stderr=stderr, env=dict(os.environ, R101_TRACE_PATH=str(out("complete"))))
if run.returncode:
    print(out("stdout").read_text(), out("stderr").read_text())
    sys.exit(run.returncode)
lines = out("stdout").read_text().splitlines()
names = [l.removeprefix("test ").removesuffix(" ... ok") for l in lines if l.startswith("test ") and l.endswith(" ... ok")]
expected = {
    path.removesuffix(".rs").replace("/", "::") + "::" + n
    for path in ("tool_display/tests.rs", "cases.rs")
    for n in re.findall(r"#\[test\]\s+fn (\w+)\(", (root / "src" / path).read_text())
}
assert len(names) == len(expected) and set(names) == expected
errs = out("stderr").read_text().splitlines()
assert errs.count("ARM " + stamp) == 1
trace = [line for line in errs if line.startswith("TRACE ")]
work = [line for line in errs if line.startswith("WORK ")]
assert len(trace) == 2 and len(work) == 7
with out("complete").open("rb") as file:
    observations = sum(1 for line in file if line.endswith(b"\n"))
assert observations == 2043 and trace[0] == f"TRACE complete-observations {observations}"
out("trace").write_text("\n".join(trace) + "\n")
out("work").write_text("ARM " + stamp + "\n" + "\n".join(work) + "\n")
after = sha(exe)
assert before == after and inputs(root) == bound
row = {"arm":stamp, "manifest":"Cargo.toml", "source":"src/lib.rs", "test":True, "fresh":False,
       "executable":exe.relative_to(warm).as_posix(), "sha256_before":before, "sha256_after":after,
       "serde_json_features":serde["features"], "profile":selected["profile"], "tests":sorted(names),
       "inputs_sha256":bound, "source_variant_sha256":sha(Path(patch)), "trace_sha256":sha(out("trace")),
       "complete_sha256":sha(out("complete")), "complete_size":out("complete").stat().st_size,
       "work_sha256":sha(out("work")), "cargo":tool("cargo"), "rustc":tool("rustc")}
out("provenance").write_text(json.dumps(row, sort_keys=True) + "\n")
print(f"PASS fresh artifact {stamp}: {len(names)}/{len(expected)} whole-module and exact approval display tests")
