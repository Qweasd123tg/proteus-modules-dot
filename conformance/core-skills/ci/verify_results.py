#!/usr/bin/env python3
"""Exact named-check gate; does not replace the Rust assertions with simulation."""
import json
from pathlib import Path
import sys


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def decode(text):
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError(f"non-finite JSON constant: {value}")))


def verify(report, stderr, expected, before, after):
    if before != after or not before.get("harness") or not before.get("portable_module"):
        raise ValueError("input source hashes changed or missing")
    if (type(report.get("schema_version")) is not int or report["schema_version"] != 1
            or report.get("core_commit") != expected["core_commit"]):
        raise ValueError("wrong report version or Core pin")
    checks = report.get("checks", [])
    names = [check.get("name") for check in checks]
    if names != expected["checks"] or len(names) != 11 or len(set(names)) != 11:
        raise ValueError("required exact ordered 11 checks not present")
    if any(check.get("status") != "passed" or not isinstance(check.get("evidence"), dict)
           for check in checks):
        raise ValueError("check did not pass or evidence missing")
    markers = [decode(line.removeprefix("SKILLS_CORE_CHECK "))
               for line in stderr.splitlines() if line.startswith("SKILLS_CORE_CHECK ")]
    if markers != [{"name": name, "status": "passed"} for name in names]:
        raise ValueError("stderr completion markers differ from exact report")
    return {"status": "passed", "core_checks": 11, "input_sources_unchanged": True}


if __name__ == "__main__":
    if len(sys.argv) != 6:
        raise SystemExit("usage: verify_results.py REPORT STDERR SCENARIOS BEFORE AFTER")
    report, stderr, expected, before, after = [Path(name) for name in sys.argv[1:]]
    print(json.dumps(verify(decode(report.read_text()), stderr.read_text(),
                            decode(expected.read_text()), decode(before.read_text()),
                            decode(after.read_text())), indent=2))
