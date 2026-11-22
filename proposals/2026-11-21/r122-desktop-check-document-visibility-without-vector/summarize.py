"""Verify byte parity and isolate the cost of the pane vector from the existing key memo."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, evidence = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers = ("pin", "after442")
stages = ("baseline", "candidate")
trace, work, counts, provenance, testnames = None, [], {}, [], None
for tier, stage in itertools.product(tiers, stages):
    prefix = raw / f"{tier}-{stage}"
    read = lambda ext: Path(f"{prefix}.{ext}").read_bytes()
    p = json.loads(read("provenance"))
    assert p["arm"] == f"{tier}/{stage}"
    assert len(p["tests"]) == 2
    assert [len(x["tests"]) for x in p["tests"]] == [72,7]
    assert all(not x["fresh"] and x["test"] and x["sha256_before"] == x["sha256_after"] for x in p["tests"])
    names = [x["tests"] for x in p["tests"]]
    if testnames is None:
        testnames = names
    assert testnames == names
    assert p["patch_sha256"] == sha((packet / "source.patch").read_bytes())
    for key, ext in (("trace_sha256", "trace"), ("trace_full_sha256", "trace-full"), ("work_sha256", "work")):
        assert p[key] == sha(read(ext))
    provenance.append(p)
    raw_trace = read("trace-full")
    assert len(raw_trace.splitlines()) == 7
    if trace is None:
        trace = raw_trace
        (packet / "behavior.trace").write_bytes(read("trace"))
    assert trace == raw_trace
    work.append(read("work").decode())
    rows = {k: json.loads(v) for k, v in re.findall(r"^WORK ([a-z-]+) (.+)$", work[-1], re.M)}
    assert set(rows) == {"cold", "warm", "warm-current", "formatter", "retained",
                         "direct-single", "direct-grid-first", "direct-grid-last",
                         "direct-grid-miss", "direct-settings"}
    counts[tier, stage] = rows
for tier in tiers:
    old, new = (counts[tier, stage] for stage in stages)
    for key in ("direct-single", "direct-grid-first", "direct-grid-last", "direct-grid-miss"):
        seen = 0 if key.endswith("miss") else 256
        assert old[key] == [256, seen, 256, 8192], (tier, key, old[key])
        assert new[key] == [256, seen, 0, 0], (tier, key, new[key])
    assert old["direct-settings"] == new["direct-settings"] == [256,0,0,0]
    assert old["warm-current"] == new["warm-current"]
    assert old["retained"] == new["retained"]
    assert old["formatter"] == new["formatter"]
    assert old["warm"][0] == new["warm"][0] == 512
    assert old["warm"][1] - new["warm"][1] == 256
    assert old["warm"][2] - new["warm"][2] == 8192
    assert old["cold"][0] == new["cold"][0] == 2
    assert old["cold"][1] - new["cold"][1] == 1
    assert old["cold"][2] - new["cold"][2] == 32
assert counts["after442","baseline"]["warm"] == [512,256,8192]
assert counts["after442","candidate"]["warm"] == [512,0,0]
assert counts["after442","baseline"]["retained"][:2] == [202,202]
assert counts["after442","baseline"]["formatter"] == [0,1,0,1,1,0,0]
assert counts["pin","baseline"]["formatter"] == [0,1,64,1,1,0,0]
assert counts["after442","baseline"]["warm-current"] == [256,0,0]
(packet / "cargo-provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
(packet / "work.log").write_text(
    "Direct rows: visibility calls, true results, allocation/reallocation requests, requested bytes. "
    "Cold/warm rows: terminal guard calls, allocation/reallocation requests, requested bytes. "
    "Memo rows model the R119 previous proof only, not new savings. "
    "Formatter counts are from a derivative independent of measured uninstrumented terminal guard.\n\n" +
    "\n".join(work))
lines = [l for l in evidence.read_text().splitlines() if l.startswith(("PASS ", "FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")]) == 4
assert lines[-1].startswith("PASS exact terminal")
(packet / "evidence.log").write_text("\n".join(lines) + "\n")
print("PASS eight fresh artifacts, 72+7 tests per stock/cumulative arm and seven byte-identical records; visibility only, memo/current unchanged.")
print("Full byte evidence SHA256", sha(trace))
