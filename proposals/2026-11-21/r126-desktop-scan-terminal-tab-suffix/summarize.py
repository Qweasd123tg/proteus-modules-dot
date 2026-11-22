"""Require fresh exact 4-arm evidence and lower normal suffix-lookup allocation traffic."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, log = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers = ("pin","after444")
arms = ("baseline","candidate")
trace, records, measurements, work_log, test_names = None, [], {}, [], None
for tier,arm in itertools.product(tiers,arms):
    prefix = raw/f"{tier}-{arm}"
    read = lambda suffix: Path(f"{prefix}.{suffix}").read_bytes()
    p = json.loads(read("provenance"))
    assert p["arm"]==f"{tier}/{arm}" and p["patch_sha256"]==sha((packet/"source.patch").read_bytes())
    tests=p["tests"]
    assert [len(x["tests"]) for x in tests]==[72,4]
    assert all(t["fresh"] is False and t["test"] is True and t["sha256_before"]==t["sha256_after"] for t in tests)
    assert len(set(tests[0]["tests"]))==72 and len(set(tests[1]["tests"]))==4
    names=[t["tests"] for t in tests]
    if test_names is None: test_names=names
    assert test_names==names
    for key,suffix in (("trace_sha256","trace"),("trace_full_sha256","trace-full"),("work_sha256","work")):
        assert p[key]==sha(read(suffix))
    records.append(p)
    full=read("trace-full")
    assert len(full.splitlines())==11
    if trace is None:
        trace=full
        (packet/"behavior.trace").write_bytes(read("trace"))
    assert trace==full
    work_log.append(read("work").decode())
    tally={k:json.loads(v) for k,v in re.findall(r"^WORK ([a-z-]+) (.+)$",work_log[-1],re.M)}
    assert set(tally)=={"no-windows","empty-window","ordinary-one","ordinary-two","ordinary-three",
                       "first-provider","enabled-provider","no-provider","bounds"}
    assert all(len(v)==4 and all(type(n) is int and n>=0 for n in v) for v in tally.values())
    measurements[tier,arm]=tally
for tier in tiers:
    a,b=(measurements[tier,arm] for arm in arms)
    for label,old in a.items():
        new=b[label]
        assert old[:2]==new[:2], (tier,label,old,new)
        assert new[2] <= old[2] and new[3] <= old[3], (tier,label,old,new)
        if label in ("ordinary-one","ordinary-two","ordinary-three"):
            assert old[0]==64 and old[1]>0 and new[2] < old[2] and new[3] < old[3],(tier,label,old,new)
lines=[line for line in log.read_text().splitlines() if line.startswith(("PASS ","FENCE "))]
assert len([line for line in lines if line.startswith("PASS fresh")]) == 4
assert lines[-1].startswith("PASS exact visible tab membership union")
(packet/"cargo-provenance.json").write_text(json.dumps(records,sort_keys=True,indent=2)+"\n")
(packet/"work.log").write_text("Fields: lookups, unique retained live IDs, allocated/reallocated requests, requested bytes. "
                              "The independent set oracle and fixture building are outside the measured lambda.\n\n"+
                              "\n".join(work_log))
(packet/"evidence.log").write_text("\n".join(lines)+"\n")
print("PASS exact tabs artifact + four focused proofs per arm; same full behavior bytes; less normal open-terminal numbering work.")
print("Full trace SHA256",sha(trace))
