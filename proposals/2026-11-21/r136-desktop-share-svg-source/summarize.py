"""Bind the final admitted run's redacted receipts to exact source/metric evidence."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, log = map(Path,sys.argv[1:])
sha=lambda data:hashlib.sha256(data).hexdigest()
patch=sha((packet/"source.patch").read_bytes())
assert patch=="04c23b711e2ab52da2a13f420689d68196928c90ed7e7d0d7656857622634a79"
tiers=("pin","after451")
arms=("baseline","candidate")
trace, names, values, work, proof = None, None, {}, [], []
for tier,arm in itertools.product(tiers,arms):
    p=raw/f"{tier}-{arm}"
    def read(ext): return Path(f"{p}.{ext}").read_bytes()
    v=json.loads(read("provenance"))
    assert v["arm"]==f"{tier}/{arm}" and v["patch_sha256"]==patch
    assert v["cargo"]["sha256"]=="841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66"
    assert v["rustc"]["sha256"]=="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
    t,=v["tests"]
    assert t["sha256_before"]==t["sha256_after"] and t["fresh"] is False and t["test"] is True
    assert len(t["tests"])==len(set(t["tests"]))==36
    if names is None:
        names=t["tests"]
    assert names==t["tests"]
    for key,ext in (("trace_sha256","trace"),("trace_full_sha256","trace-full"),("work_sha256","work")):
        assert v[key]==sha(read(ext))
    curr=read("trace-full")
    assert len(curr.splitlines())==4
    if trace is None:
        trace=curr
        (packet/"behavior.trace").write_bytes(read("trace"))
    assert trace==curr
    proof.append(v)
    work.append(read("work").decode())
    table={k:json.loads(row) for k,row in re.findall(r"^WORK ([a-z-]+) (.+)$",work[-1],re.M)}
    assert len(table)==8
    values[tier,arm]=table
assert all(values["pin",arm]==values["after451",arm] for arm in arms)
old,new = (values["pin",arm] for arm in arms)
assert [old["decode-live"],old["prepare-live"]]==[[43914,32,801740,43914],[43914,20,755142,44140]]
assert [new["decode-live"],new["prepare-live"]]==[[43914,33,801780,43954],[43914,18,667196,172]]
assert [old["equal-redecode-live"],new["equal-redecode-live"]]==[[43914,87,2402724,88126],[43914,86,2270880,88152]]
lines=[l for l in log.read_text().splitlines() if l.startswith(("PASS ","FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")])==4
assert lines[-1]=="PASS real typed/validation/cache/svg budget; no native rendering/network/extension/process executed"
(packet/"cargo-provenance.json").write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
(packet/"work.log").write_text("Fields: source UTF-8 bytes, allocation/reallocation requests, aggregate requested bytes, net requested live byte delta. "
                              "The ordered decode/preparation sum is the comparison, not allocator RSS.\n\n"
                              +"\n".join(work))
(packet/"evidence.log").write_text("\n".join(lines)+"\n")
print("PASS four admitted arms, identical exact guard and behavior records",sha(trace))
