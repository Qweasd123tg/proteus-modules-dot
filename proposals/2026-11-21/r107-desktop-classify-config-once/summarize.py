"""Compare all ordered static-tree outputs and scoped lookup/work counters."""
from pathlib import Path
import hashlib
import json
import re
import sys

raw,out=map(Path,sys.argv[1:])
arms=("pin-baseline","pin-candidate","after429-baseline","after429-candidate")
provenance,work_log,counts=[],[],{}
trace=None
sha=lambda b:hashlib.sha256(b).hexdigest()
for arm in arms:
    stem=raw/arm
    def suffix(ext):
        return Path(f"{stem}.{ext}")
    p=json.loads(suffix("provenance").read_text())
    assert p["arm"]==arm.replace("-","/") and not p["fresh"] and p["test"]
    assert p["sha256_before"]==p["sha256_after"] and len(p["tests"])==10
    if trace is None:
        trace=suffix("trace").read_bytes()
    assert suffix("trace").read_bytes()==trace and p["trace_sha256"]==sha(trace)
    work=suffix("work").read_bytes()
    assert p["work_sha256"]==sha(work)
    rows={key:json.loads(values) for key,values in re.findall(r"^WORK ([a-z-]+): (\[.*\])$",work.decode(),re.M)}
    assert len(rows)==7 and all(len(v)==9 for v in rows.values())
    counts[arm]=rows
    provenance.append(p)
    work_log.append(work.decode())
for tier in ("pin","after429"):
    old,new=(counts[f"{tier}-{arm}"] for arm in ("baseline","candidate"))
    assert old["portable"]==[19,1,2,8,2,14,8,8,65063]
    assert old["types"]==[23,1,5,5,4,17,4,4,127]
    assert old["label-byte-sum"]==[69,0,2,34,2,35,34,32,8388608]
    for label,row in old.items():
        assert new[label][1:]==row[1:]
        delta={"portable":8,"types":8,"label-byte-sum":34}.get(label,0)
        assert new[label][0]==row[0]-delta
assert counts["pin-baseline"]==counts["after429-baseline"]
assert counts["pin-candidate"]==counts["after429-candidate"]
(out/"cargo-provenance.json").write_text(json.dumps(provenance,sort_keys=True,indent=2)+"\n")
(out/"behavior.trace").write_bytes(trace)
(out/"work.log").write_text(
    "Counter order: entry type metadata lookups, current path canonicalizations, directory "
    "canonicalizations, eligible file canonicalizations, directory reads, visited entries, "
    "label requests, profile-open attempts, bytes read for labels.\n\n"+"\n".join(work_log)
)
print("PASS four exact config-picker traces",sha(trace),"10/10 each; only classification counts differ")
