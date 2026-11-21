#!/usr/bin/env python3
import json
import pathlib
import re
import sys

log = pathlib.Path(sys.argv[1]).read_text()
expected_fields = [
    "tuple_bytes",
    "hash_calls",
    "hash_requested",
    "cas_calls",
    "cas_requested",
    "retry_calls",
    "retry_requested",
    "receipt",
]
groups = {}
for line in log.splitlines():
    match = re.fullmatch(r"R66 (deletion|selection|bulk) old=(true|false) (.*)", line)
    if not match:
        continue
    label, old, values = match.groups()
    raw = dict(token.split("=", 1) for token in values.split(" "))
    assert list(raw) == expected_fields and re.fullmatch("[0-9a-f]{64}", raw["receipt"])
    raw = {k: int(v) if k != "receipt" else v for k, v in raw.items()}
    groups.setdefault(label, []).append({"old": old == "true", **raw})
assert list(groups) == ["deletion", "selection", "bulk"]
for label, pairs in groups.items():
    assert len(pairs) == 4 and [pair["old"] for pair in pairs] == [True, False, False, True]
    assert len({pair["tuple_bytes"] for pair in pairs}) == len({pair["receipt"] for pair in pairs}) == 1
    for old, new in [(pairs[0], pairs[1]), (pairs[3], pairs[2])]:
        assert all(old[k] > new[k] for k in expected_fields[1:-1]), (old, new)
counts = re.search(r"test result: ok\. (\d+) passed; 0 failed; (\d+) ignored;", log)
assert counts and int(counts.group(1)) >= 65
print(json.dumps({"native_tests_passed": int(counts.group(1)),
                  "native_tests_ignored": int(counts.group(2)),
                  "allocator_order": "stock/candidate/candidate/stock, own thread",
                  "samples": groups}, indent=2))
