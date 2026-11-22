"""Bind canonical terminal key/guard parity and the scoped memo tradeoff."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, evidence = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers = ("pin", "after440")
stages = ("baseline", "candidate")
trace, work, counts, provenance, testnames = None, [], {}, [], None
for tier, stage in itertools.product(tiers, stages):
    prefix = raw / f"{tier}-{stage}"
    read = lambda ext: Path(f"{prefix}.{ext}").read_bytes()
    p = json.loads(read("provenance"))
    assert p["arm"] == f"{tier}/{stage}" and p["test"] and not p["fresh"]
    assert len(p["tests"]) == 4 and p["sha256_before"] == p["sha256_after"]
    if testnames is None:
        testnames = p["tests"]
    assert testnames == p["tests"]
    assert p["patch_sha256"] == sha((packet / "source.patch").read_bytes())
    for key, ext in (("trace_sha256", "trace"), ("trace_full_sha256", "trace-full"), ("work_sha256", "work")):
        assert p[key] == sha(read(ext))
    provenance.append(p)
    raw_trace = read("trace-full")
    assert len(raw_trace.splitlines()) == 4
    if trace is None:
        trace = raw_trace
        (packet / "behavior.trace").write_bytes(read("trace"))
    assert trace == raw_trace
    work.append(read("work").decode())
    rows = {k: json.loads(v) for k, v in re.findall(r"^WORK ([a-z-]+) (.+)$", work[-1], re.M)}
    assert set(rows) == {"cold", "warm", "warm-current", "formatter", "retained"}
    counts[tier, stage] = rows
for stage in stages:
    assert counts["pin", stage] == counts["after440", stage]
old, new = (counts["pin", stage] for stage in stages)
assert old["formatter"] == [0,1,64,1,1,0,0] and new["formatter"] == [0,1,0,1,1,0,0]
assert old["retained"] == [0,0,112,24] and new["retained"] == [202,202,136,24]
assert old["cold"] == [2,9,1234] and new["cold"] == [2,5,633]
assert old["warm"] == [512,2304,315904] and new["warm"] == [512,256,8192]
assert old["warm-current"] == [256,1024,153856] and new["warm-current"] == [256,0,0]

(packet / "cargo-provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
(packet / "work.log").write_text(
    "Cold/warm rows: calls to guard predicates, alloc/realloc requests, requested bytes. "
    "Retained row: key bytes, key String capacity, inline bytes of lifted Remote subset, inline bytes of OnceCell<String>. "
    "Formatter row: encoder invocations in instrumented derivative, for wrong connection, first visible, "
    "64 repeated guards, first current on another viewer, Settings-covered but eligible connection, missing API, and dead workspace.\n\n"
    + "\n".join(work))
lines = [l for l in evidence.read_text().splitlines() if l.startswith(("PASS ", "FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")]) == 4
(packet / "evidence.log").write_text("\n".join(lines) + "\n")
print("PASS four exact 4/4 arms and four full byte records, canonical guard and bounded per-view memo tradeoff.")
print("Full byte evidence SHA256", sha(trace))
