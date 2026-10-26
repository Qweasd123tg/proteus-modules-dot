"""Fail closed on incomplete authored Rust test evidence; no Cargo invocation."""
import json
import re
import sys
from pathlib import Path

SUMMARY = re.compile(
    r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; "
    r"(\d+) ignored; (\d+) measured; (\d+) filtered out;", re.MULTILINE
)
CASE = re.compile(r"^test (\S+) \.\.\. (ok|ignored|FAILED)(?:[ \t].*)?$", re.MULTILINE)


class EvidenceError(ValueError):
    pass


def verify(stdout, required, before, after):
    if before != after:
        raise EvidenceError("source manifest changed during gate execution")
    expected = required["test_names"]
    if len(expected) != 33 or len(set(expected)) != 33:
        raise EvidenceError("required test manifest must name exactly 33 distinct cases")
    cases = CASE.findall(stdout)
    names = [name for name, _ in cases]
    if len(names) != 33 or set(names) != set(expected):
        raise EvidenceError("individual case names do not match the 33 required cases")
    if any(status != "ok" for _, status in cases):
        raise EvidenceError("a required individual case did not pass")
    summaries = SUMMARY.findall(stdout)
    if len(summaries) != 5:
        raise EvidenceError("expected five complete package test summaries")
    counts = []
    for status, passed, failed, ignored, measured, filtered in summaries:
        if status != "ok" or any(int(value) != 0 for value in (failed, ignored, measured, filtered)):
            raise EvidenceError("test summary contains failed, ignored, measured or filtered cases")
        counts.append(int(passed))
    if sorted(counts) != [0, 0, 2, 12, 19] or sum(counts) != 33:
        raise EvidenceError("suite totals do not match 2 controls, 12 typed, 19 lifecycle cases")
    return {"accepted": True, "passed": 33, "failed": 0, "ignored": 0,
            "filtered": 0, "source_unchanged": True, "test_names": sorted(names)}


def main():
    if len(sys.argv) != 5:
        raise EvidenceError("usage: verify_results.py stdout required before after")
    stdout = Path(sys.argv[1]).read_text()
    required, before, after = [json.loads(Path(path).read_text()) for path in sys.argv[2:]]
    print(json.dumps(verify(stdout, required, before, after), indent=2))


if __name__ == "__main__":
    try:
        main()
    except (EvidenceError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"evidence rejected: {error}", file=sys.stderr)
        raise SystemExit(1)
