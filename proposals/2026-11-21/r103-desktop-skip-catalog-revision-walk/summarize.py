"""Compare actual work and full results across the exact fresh source arms."""
from pathlib import Path
import hashlib
import json
import re
import sys

raw, out = map(Path, sys.argv[1:])
arms = ("pin-baseline", "pin-candidate", "after425-baseline", "after425-candidate")
provenance, work_log, all_work = [], [], {}
sha = lambda b: hashlib.sha256(b).hexdigest()
trace = None
for arm in arms:
    stem = raw / arm
    def suffix(ext):
        return Path(f"{stem}.{ext}")
    p = json.loads(suffix("provenance").read_text())
    assert p["arm"] == arm.replace("-", "/") and not p["fresh"] and p["test"]
    assert p["sha256_before"] == p["sha256_after"] and len(p["tests"]) == 23
    if trace is None:
        trace = suffix("trace").read_bytes()
    assert suffix("trace").read_bytes() == trace and p["trace_sha256"] == sha(trace)
    work = suffix("work").read_bytes()
    assert p["work_sha256"] == sha(work)
    rows={key:json.loads(counts) for key,counts in re.findall(r"^WORK ([a-z-]+): (\[.*\])$",work.decode(),re.M)}
    assert len(rows) == 4 and all(len(v) == 8 for v in rows.values())
    all_work[arm] = rows
    provenance.append(p)
    work_log.append(work.decode())

for tier in ("pin", "after425"):
    a, b = (all_work[f"{tier}-{name}"] for name in ("baseline","candidate"))
    for label, expected in (("ordinary",[1,14,1,1,1,14,41,152]),("synthetic",[2,18,2,2,2,10,12,13])):
        assert a[label+"-runtime"] == b[label+"-runtime"] == a[label+"-inventory"] == expected
        assert b[label+"-inventory"] == expected[:5] + [0,0,0]
assert all_work["pin-baseline"] == all_work["after425-baseline"]
assert all_work["pin-candidate"] == all_work["after425-candidate"]
(out/"cargo-provenance.json").write_text(json.dumps(provenance,sort_keys=True,indent=2)+"\n")
(out/"behavior.trace").write_bytes(trace)
(out/"work.log").write_text(
    "Counter order: discovery-root read_dir, manifest load, instruction package canonicalize, "
    "instruction directory canonicalize, instruction file canonicalize, revision, "
    "revision read_dir, revision entry metadata.\n\n" + "\n".join(work_log)
)
print("PASS four exact behavior traces",sha(trace),"23/23 tests per arm; ordinary/synthetic stock and cumulative work agree")
