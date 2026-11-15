#!/usr/bin/env python3
"""Bounded local validation: Python controls and manifests only, never Cargo/gates."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "checks-v2"
OUT.mkdir(exist_ok=False)
RESULTS = []


def run(label, args, cwd, expected=0, contains=None):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                            timeout=30, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    (OUT / (label + ".stdout")).write_text(result.stdout)
    (OUT / (label + ".stderr")).write_text(result.stderr)
    valid = (result.returncode == expected if expected is not None else result.returncode != 0)
    if contains:
        valid = valid and contains in result.stdout + result.stderr
    RESULTS.append({"label": label, "exit_code": result.returncode, "expected_exit": expected,
                    "expected_text": contains, "matched": valid})
    if not valid:
        raise AssertionError((label, result.returncode, result.stderr))
    return result


python = [sys.executable, "-B", "-I"]
for variant in ("before", "candidate"):
    tree = ROOT / variant
    for lane in ("core-skills", "current-core-skills"):
        package = tree / "conformance" / lane
        owner = package if variant == "before" else tree / "conformance/core-skills"
        for script, count in (("test_capture_controls.py", 4), ("test_verify_results.py", 11)):
            args = python + [str(owner / "ci" / script)]
            if variant == "candidate" and lane == "current-core-skills" and count == 11:
                args.append("scenarios.json")
            label = variant + "-" + lane + "-" + script.removesuffix(".py")
            result = run(label, args, package, contains=f"Ran {count} tests")
            if not re.search(r"\nOK\s*$", result.stderr) or "skipped=" in result.stderr:
                raise AssertionError(label)
            RESULTS[-1]["methods_passed"] = count
        run(variant + "-" + lane + "-freeze", ["sha256sum", "-c", "CODE.sha256"], package)
        run(variant + "-" + lane + "-manifest", python + [str(package / "ci/source_manifest.py"),
            str(tree / "examples/portable-skill-catalog")], ROOT)
        run(variant + "-" + lane + "-shell", ["bash", "-n", str(package / "ci/run.sh")], ROOT)

# Every newly shared implementation/test file is covered by the current lane's freeze.
mutation = OUT / "mutation"
shutil.copytree(ROOT / "candidate", mutation)
package = mutation / "conformance/current-core-skills"
owner = mutation / "conformance/core-skills/ci"
for name in ("run_probe.py", "verify_results.py", "test_capture_controls.py", "test_verify_results.py"):
    path = owner / name
    original = path.read_bytes()
    path.write_bytes(original + b"\n# deliberate source mutation\n")
    try:
        run("reject-mutation-" + name.removesuffix(".py"), python + [str(package / "ci/source_manifest.py"),
            str(mutation / "examples/portable-skill-catalog")], ROOT, expected=None,
            contains="frozen shared CI source input set or bytes changed")
    finally:
        path.write_bytes(original)
missing = owner / "run_probe.py"
original = missing.read_bytes()
missing.unlink()
try:
    run("reject-missing-shared", python + [str(package / "ci/source_manifest.py"),
        str(mutation / "examples/portable-skill-catalog")], ROOT, expected=None,
        contains="not a regular source input: run_probe.py")
finally:
    missing.write_bytes(original)
run("restored-manifest", python + [str(package / "ci/source_manifest.py"),
    str(mutation / "examples/portable-skill-catalog")], ROOT)

# Exercise the exact final Python post-resolution check without executing the
# surrounding lock_only shell/Cargo commands. Cargo.lock alone may change.
lock_script = (package / "ci/lock_only.sh").read_text()
post_check = lock_script.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
post = OUT / "post-resolution"
post.mkdir()
(post / "source-hashes-before.json").write_text((OUT / "restored-manifest.stdout").read_text())
post_args = python + ["-c", post_check, str(post / "source-hashes-before.json"),
                      str(mutation / "examples/portable-skill-catalog")]
run("post-resolution-valid", post_args, package, contains="shared CI and other frozen sources unchanged")
shared = owner / "verify_results.py"
original = shared.read_bytes()
shared.write_bytes(original + b"\n# deliberate post-resolution mutation\n")
try:
    run("post-resolution-reject-shared-change", post_args, package, expected=None, contains="shared_ci")
finally:
    shared.write_bytes(original)
lock = package / "Cargo.lock"
original = lock.read_bytes()
lock.write_bytes(original + b"\n# deliberate lock-only resolution change\n")
try:
    run("post-resolution-allows-lock-change", post_args, package, contains="Only variant Cargo.lock may differ")
finally:
    lock.write_bytes(original)

# Real verifier CLI: each lane accepts its own pin and rejects the other pin.
fixtures = OUT / "fixtures"
fixtures.mkdir()
tree = ROOT / "candidate"
lanes = ("core-skills", "current-core-skills")
source = {"harness": {"a": "hash"}, "portable_module": {"b": "hash"}, "shared_ci": {"c": "hash"}}
for name in ("before", "after"):
    (fixtures / (name + ".json")).write_text(json.dumps(source))
for report_lane in lanes:
    expected = json.loads((tree / "conformance" / report_lane / "scenarios.json").read_text())
    report = {"schema_version": 1, "core_commit": expected["core_commit"],
              "checks": [{"name": name, "status": "passed", "evidence": {}} for name in expected["checks"]]}
    (fixtures / "report.json").write_text(json.dumps(report))
    (fixtures / "stderr.txt").write_text("\n".join("SKILLS_CORE_CHECK " + json.dumps({"name": name, "status": "passed"})
        for name in expected["checks"]))
    for expected_lane in lanes:
        same = report_lane == expected_lane
        run("pin-" + report_lane + "-vs-" + expected_lane,
            python + [str(tree / "conformance/core-skills/ci/verify_results.py"), str(fixtures / "report.json"),
                str(fixtures / "stderr.txt"), str(tree / "conformance" / expected_lane / "scenarios.json"),
                str(fixtures / "before.json"), str(fixtures / "after.json")], ROOT,
            expected=0 if same else None, contains='"status": "passed"' if same else "wrong report version or Core pin")
changed = json.loads(json.dumps(source))
changed["shared_ci"]["c"] = "changed"
(fixtures / "after.json").write_text(json.dumps(changed))
run("reject-changed-shared-attestation", python + [str(tree / "conformance/core-skills/ci/verify_results.py"),
    str(fixtures / "report.json"), str(fixtures / "stderr.txt"),
    str(tree / "conformance/current-core-skills/scenarios.json"), str(fixtures / "before.json"),
    str(fixtures / "after.json")], ROOT, expected=None, contains="input source hashes changed or missing")

before_help = run("before-probe-help", python + [str(ROOT / "before/conformance/current-core-skills/ci/run_probe.py"), "--help"], ROOT)
after_help = run("candidate-probe-help", python + [str(tree / "conformance/core-skills/ci/run_probe.py"), "--help"], ROOT)
assert before_help.stdout == after_help.stdout
run("reject-extra-scenarios-arguments", python + [str(tree / "conformance/core-skills/ci/test_verify_results.py"), "a", "b"], ROOT,
    expected=None, contains="usage: test_verify_results.py [SCENARIOS]")
(OUT / "RESULTS.json").write_text(json.dumps({"python": sys.version, "checks": RESULTS}, indent=2) + "\n")
print(json.dumps({"checks": len(RESULTS), "matched": sum(x["matched"] for x in RESULTS),
                  "suite_method_executions": sum(x.get("methods_passed", 0) for x in RESULTS)}))
