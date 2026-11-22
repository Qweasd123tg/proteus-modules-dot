"""Verify byte-identical layout decisions and account for only the removed vector."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, evidence = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers = ("pin", "after438")
stages = ("baseline", "candidate")
trace, work, counts, provenance, testnames = None, [], {}, [], None
for tier, stage in itertools.product(tiers, stages):
    prefix = raw / f"{tier}-{stage}"
    read = lambda ext: Path(f"{prefix}.{ext}").read_bytes()
    p = json.loads(read("provenance"))
    assert p["arm"] == f"{tier}/{stage}"
    assert len(p["tests"]) == 2
    assert [len(x["tests"]) for x in p["tests"]] == [72,3]
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
    assert len(raw_trace.splitlines()) == 10
    if trace is None:
        trace = raw_trace
        (packet / "behavior.trace").write_bytes(read("trace"))
    assert trace == raw_trace
    work.append(read("work").decode())
    rows = {k: json.loads(v) for k, v in re.findall(r"^WORK ([a-z-]+) (.+)$", work[-1], re.M)}
    assert set(rows) == {"single", "two", "grid", "wide", "empty-single", "locked-holder",
                         "locked-empty", "empty-fixed-transient", "empty-split", "duplicate-nested"}
    counts[tier, stage] = rows
for tier in tiers:
    before, after = (counts[tier, stage] for stage in stages)
    for label, old in before.items():
        new = after[label]
        assert len(old) == len(new) == 5 and old[0] == new[0]
        assert new[1:3] == [0,0]
        assert old[3] - new[3] == old[0] * old[1]
        assert old[4] - new[4] == old[0] * old[2]
assert counts["pin","baseline"]["single"] == [1,1,32,2,64]
assert counts["after438","baseline"]["single"] == [1,1,32,1,32]
assert counts["after438","candidate"]["single"] == [1,0,0,0,0]
assert counts["after438","baseline"]["grid"] == [4,1,32,4,128]
assert counts["after438","baseline"]["wide"] == [12,3,224,36,2688]
(packet / "cargo-provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
(packet / "work.log").write_text(
    "Fields: pane count, scalar alloc/realloc requests, scalar requested bytes, "
    "controls sweep alloc/realloc requests, controls sweep requested bytes. "
    "One controls expression per existing pane; fixtures/output preallocated.\n\n" + "\n".join(work))
lines = [l for l in evidence.read_text().splitlines() if l.startswith(("PASS ", "FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")]) == 4
(packet / "evidence.log").write_text("\n".join(lines) + "\n")
print("PASS eight fresh artifacts, 72+3 tests per stock/cumulative arm, ten exact byte records; requests equal removed count cost.")
print("Full byte evidence SHA256", sha(trace))
