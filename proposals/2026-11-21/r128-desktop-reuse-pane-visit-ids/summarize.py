"""Prove exact behavior parity and branch-local Pane::show allocation accounting."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, log = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers, arms = ("pin","after447"), ("baseline","candidate")
trace, proof, values, work, names = None, [], {}, [], None
for tier,arm in itertools.product(tiers,arms):
    p = raw/f"{tier}-{arm}"
    read = lambda ext: Path(f"{p}.{ext}").read_bytes()
    v = json.loads(read("provenance"))
    assert v["arm"]==f"{tier}/{arm}"
    assert v["patch_sha256"]==sha((packet/"source.patch").read_bytes())
    assert [len(t["tests"]) for t in v["tests"]]==[72,4]
    assert all(t["fresh"] is False and t["test"] is True and t["sha256_before"]==t["sha256_after"] for t in v["tests"])
    n=[t["tests"] for t in v["tests"]]
    assert all(len(t)==len(set(t)) for t in n)
    if names is None: names=n
    assert n==names
    for key,ext in (("trace_sha256","trace"),("trace_full_sha256","trace-full"),("work_sha256","work")):
        assert v[key]==sha(read(ext))
    new=read("trace-full")
    assert len(new.splitlines())==4
    if trace is None:
        trace=new
        (packet/"behavior.trace").write_bytes(read("trace"))
    assert trace==new
    proof.append(v)
    work.append(read("work").decode())
    table={k:json.loads(n) for k,n in re.findall(r"^WORK ([a-z-]+) (.+)$",work[-1],re.M)}
    assert set(table)=={"same-active","alternate","first-visit","restored-active","missing",
                       "duplicate-different","duplicate-equal","empty-active"}
    assert all(len(r)==4 and all(type(x) is int and x>=0 for x in r) for r in table.values())
    values[tier,arm]=table
for tier in tiers:
    before,after=(values[tier,a] for a in arms)
    for label,b in before.items():
        a=after[label]
        count,bytes_=b[:2]
        assert a[:2]==b[:2]
        if label in ("same-active","duplicate-equal"):
            assert b[2:]==[2*count,2*bytes_] and a[2:]==[0,0],(label,b,a)
        elif label in ("alternate","duplicate-different"):
            assert b[2:]==[2*count,2*bytes_] and a[2:]==[count,bytes_],(label,b,a)
        elif label=="first-visit":
            assert b[2:]==a[2:]==[2*count,2*bytes_]
        elif label=="restored-active":
            assert count==1 and b[2:]==[3,a[3]+bytes_] and a[2]==2 and a[3]>bytes_
        elif label in ("missing","empty-active"):
            assert b[2:]==a[2:]==[0,0]
assert all(values["pin",a]==values["after447",a] for a in arms)
lines=[l for l in log.read_text().splitlines() if l.startswith(("PASS ","FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")])==4
assert lines[-1].startswith("PASS exact history/MRU")
(packet/"cargo-provenance.json").write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
(packet/"work.log").write_text("Fields: Pane::show calls, requested ID UTF-8 bytes, alloc/realloc requests, "
                              "aggregate requested bytes. Prebuilt fixtures and comparators are outside the meter.\n\n" +
                              "\n".join(work))
(packet/"evidence.log").write_text("\n".join(lines)+"\n")
print("PASS stock/cumulative direct exact MRU, state and close-fallback byte parity; branch-local request and byte reductions")
print("Full byte evidence SHA256",sha(trace))
