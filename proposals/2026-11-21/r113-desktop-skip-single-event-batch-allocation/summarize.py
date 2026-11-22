"""Compare exact trace bytes and reject any scoped batch allocation regression."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, evidence = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers = ("pin", "after434")
stages = ("baseline", "candidate")
trace, work, counts, provenance = None, [], {}, []
for tier, stage in itertools.product(tiers, stages):
    prefix = raw / f"{tier}-{stage}"
    read = lambda ext: Path(f"{prefix}.{ext}").read_bytes()
    p = json.loads(read("provenance"))
    assert p["arm"] == f"{tier}/{stage}" and not p["fresh"] and p["test"]
    assert len(p["tests"]) == 14 and p["sha256_before"] == p["sha256_after"]
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
    rows = {int(n): json.loads(v) for n, v in re.findall(r"^WORK burst-(\d+) (.+)$", work[-1], re.M)}
    assert set(rows) == {1, 2, 4, 5, 8, 32, 127, 128}
    counts[tier, stage] = rows
for stage in stages:
    assert counts["pin", stage] == counts["after434", stage]
before, after = (counts["pin", stage] for stage in stages)
for n, old in before.items():
    new = after[n]
    assert len(old) == len(new) == 5 and old[0] == new[0] == n
    assert new[1] < old[1] and new[2] < old[2]
    assert old[3:] == new[3:] == [168, 280]
assert before[1][:3] == [1, 2, 240] and after[1][:3] == [1, 1, 72]
assert before[128][:3] == [128, 8, 42576] and after[128][:3] == [128, 7, 42408]
(packet / "cargo-provenance.json").write_text(json.dumps(provenance, sort_keys=True, indent=2) + "\n")
(packet / "work.log").write_text(
    "Fields: number of available events, alloc/realloc requests, aggregate requested bytes, "
    "sizeof(Event), size_of_val(lifted future). Ready successful first poll only; no fixture/record "
    "creation, waiting, closing or serialization. Recorders preallocate their buffers.\n\n" + "\n".join(work))
lines = [l for l in evidence.read_text().splitlines() if l.startswith(("PASS ", "FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")]) == 4
(packet / "evidence.log").write_text("\n".join(lines) + "\n")
print("PASS four 14/14 arms, four full byte traces, eight ready-burst sizes; no requested heap or lifted-frame regression.")
print("Full byte evidence SHA256", sha(trace))
