#!/usr/bin/env python3
"""Require every exact named helper control and one clean unittest summary."""
import json
from pathlib import Path
import re
import sys

CASE = re.compile(r"^(test_[a-z0-9_]+) \(__main__\.Controls\.\1\) \.\.\. ok$")
SUMMARY = re.compile(r"^Ran (\d+) tests? in [0-9.]+s$")


def verify(text, required):
    names = []
    summaries = []
    lines = text.splitlines()
    for line in lines:
        if line.startswith("test_"):
            match = CASE.fullmatch(line)
            if not match:
                raise ValueError("helper control not an exact passing case")
            names.append(match.group(1))
        match = SUMMARY.fullmatch(line)
        if match:
            summaries.append(int(match.group(1)))
    if names != required or len(names) != len(set(names)):
        raise ValueError("helper exact named cases differ")
    if summaries != [len(required)] or lines.count("OK") != 1 or any(line.startswith("FAILED") for line in lines):
        raise ValueError("helper clean single summary missing")
    return {"passed": len(required), "exact_names": names}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_helper_logs.py RESULTS REQUIRED_NAMES_JSON")
    root, names_path = map(Path, sys.argv[1:])
    expected = json.loads(names_path.read_text())
    observed = {}
    for name, required in expected.items():
        if (root / (name + ".exit")).read_text().strip() != "0":
            raise ValueError("helper command failed")
        observed[name] = verify((root / (name + ".stderr")).read_text(), required)
    print(json.dumps({"helper_coverage": "passed", "phases": observed}, indent=2))


if __name__ == "__main__":
    main()
