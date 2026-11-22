"""Verify exact live delta bytes and reject anything other than the predicted ID-copy savings."""
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

raw, packet, evidence = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers = ("pin", "after436")
stages = ("baseline", "candidate")
trace, work, counts, provenance = None, [], {}, []
for tier, stage in itertools.product(tiers, stages):
    prefix = raw / f"{tier}-{stage}"
    read = lambda ext: Path(f"{prefix}.{ext}").read_bytes()
    p = json.loads(read("provenance"))
    assert p["arm"] == f"{tier}/{stage}" and not p["fresh"] and p["test"]
    assert len(p["tests"]) == 17 and p["sha256_before"] == p["sha256_after"]
    assert p["patch_sha256"] == sha((packet / "source.patch").read_bytes())
    for key, ext in (("trace_sha256", "trace"), ("trace_full_sha256", "trace-full"), ("work_sha256", "work")):
        assert p[key] == sha(read(ext))
    provenance.append(p)
    raw_trace = read("trace-full")
    if trace is None:
        trace = raw_trace
        (packet / "behavior.trace").write_bytes(read("trace"))
    assert trace == raw_trace
    work.append(read("work").decode())
    rows = {k: json.loads(v) for k, v in re.findall(r"^WORK ([a-z0-9-]+) (.+)$", work[-1], re.M)}
    assert set(rows) == {"ordinary-live-128", "first-fragments", "mixed-existing", "ignored-existing", "empty-identity"}
    counts[tier, stage] = rows
for stage in stages:
    assert counts["pin", stage] == counts["after436", stage]
before, after = (counts["pin", stage] for stage in stages)
assert before["ordinary-live-128"] == [128, 256, 10496, 512, 178467]
assert after["ordinary-live-128"] == [128, 256, 10496, 256, 167971]
assert before["first-fragments"][:3] == [3, 6, 55]
for key, old in before.items():
    new = after[key]
    assert len(old) == len(new) == 5 and old[:3] == new[:3]
    factor = 2 if key == "first-fragments" else 1
    assert old[3] - new[3] == factor * old[1]
    assert old[4] - new[4] == factor * old[2]
(packet / "cargo-provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
(packet / "work.log").write_text(
    "Fields: live fragments, nonempty ID strings, ID UTF-8 bytes, alloc/realloc requests, "
    "aggregate requested bytes; scope lifted live fold and unchanged conditional trim only.\n\n" + "\n".join(work))
lines = [l for l in evidence.read_text().splitlines() if l.startswith(("PASS ", "FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")]) == 4
(packet / "evidence.log").write_text("\n".join(lines) + "\n")
print("PASS 4x 17/17 tests, four exact byte snapshot rows, five work fixtures; savings precisely nonempty ID counts and bytes.")
print("Full byte evidence SHA256", sha(trace))
