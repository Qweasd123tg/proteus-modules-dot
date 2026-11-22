"""Check full result parity and the provider-only work reduction on both source tiers."""
from pathlib import Path
import hashlib
import json
import re
import sys

raw, out = map(Path, sys.argv[1:])
arms = ("pin-baseline", "pin-candidate", "after427-baseline", "after427-candidate")
provenance, work_log, all_work = [], [], {}
sha = lambda b: hashlib.sha256(b).hexdigest()
trace = None
for arm in arms:
    stem=raw/arm
    def suffix(ext):
        return Path(f"{stem}.{ext}")
    p=json.loads(suffix("provenance").read_text())
    assert p["arm"]==arm.replace("-","/") and not p["fresh"] and p["test"]
    assert p["sha256_before"]==p["sha256_after"] and len(p["tests"])==27
    if trace is None:
        trace=suffix("trace").read_bytes()
    assert suffix("trace").read_bytes()==trace and p["trace_sha256"]==sha(trace)
    work=suffix("work").read_bytes()
    assert p["work_sha256"]==sha(work)
    rows={key:json.loads(counts) for key,counts in re.findall(r"^WORK ([a-z-]+): (\[.*\])$",work.decode(),re.M)}
    assert len(rows)==5 and all(len(v)==16 for v in rows.values())
    all_work[arm]=rows
    provenance.append(p)
    work_log.append(work.decode())

for tier, revisions in (("pin",[14,41,152]),("after427",[0,0,0])):
    a,b=(all_work[f"{tier}-{arm}"] for arm in ("baseline","candidate"))
    manifest_work=[2,14,1,1,1]
    override_work=[2,15,1,1,1]
    module_work=[1,11,8,5,12,9,6,106]
    full_work=module_work[:4]+[0,0,0,0]
    assert a["provider"]==manifest_work+revisions+module_work
    assert a["provider-with-broken-extension"]==override_work+revisions+module_work
    for label in ("provider","provider-with-broken-extension","absent-backend"):
        assert b[label]==[0]*8+a[label][8:]
    assert a["catalog"]==b["catalog"]==manifest_work+revisions+full_work
    assert a["catalog-with-broken-extension"]==b["catalog-with-broken-extension"]==override_work+revisions+full_work
    assert a["absent-backend"]==manifest_work+revisions+[0,0,0,0,1,1,1,22]
(out/"cargo-provenance.json").write_text(json.dumps(provenance,sort_keys=True,indent=2)+"\n")
(out/"behavior.trace").write_bytes(trace)
(out/"work.log").write_text(
    "Counter order: extension root read_dir, extension manifest load, instruction package/directory/file "
    "canonicalize (three counters), extension revision, revision read_dir, revision entry metadata, "
    "module directory read_dir, inventory module manifest metadata/read/program checks (three counters), "
    "provider manifest metadata/read (two counters), provider program open, bytes passed to SHA-256.\n\n"
    +"\n".join(work_log)
)
print("PASS four exact provider/catalog traces",sha(trace),"27/27 tests each, module work invariant")
