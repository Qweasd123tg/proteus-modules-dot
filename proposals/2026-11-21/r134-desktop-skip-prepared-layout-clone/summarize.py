"""Read only the corrected run receipts and emit bounded non-private evidence."""
from pathlib import Path
import hashlib
import itertools
import json
import re
import sys

raw, packet, log = map(Path, sys.argv[1:])
sha = lambda b: hashlib.sha256(b).hexdigest()
tiers, arms = ("pin", "after449"), ("baseline", "candidate")
trace, proof, values, work, names = None, [], {}, [], None
patch = sha((packet/"source.patch").read_bytes())
assert patch == "87700fd236ca0a04086ae3f8a88e29c54166157c750feaf285cbd6abb7a9634e"
for tier, arm in itertools.product(tiers, arms):
    p = raw/f"{tier}-{arm}"
    read = lambda ext: Path(f"{p}.{ext}").read_bytes()
    v = json.loads(read("provenance"))
    assert v["arm"] == f"{tier}/{arm}" and v["patch_sha256"] == patch
    assert v["cargo"]["sha256"] == "841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66"
    assert v["rustc"]["sha256"] == "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
    assert [len(t["tests"]) for t in v["tests"]] == [72, 4]
    assert all(t["fresh"] is False and t["test"] is True and t["sha256_before"] == t["sha256_after"] for t in v["tests"])
    n = [t["tests"] for t in v["tests"]]
    assert all(len(t) == len(set(t)) for t in n)
    if names is None:
        names = n
    assert n == names
    for key, ext in (("trace_sha256","trace"), ("trace_full_sha256","trace-full"), ("work_sha256","work")):
        assert v[key] == sha(read(ext))
    new = read("trace-full")
    assert len(new.splitlines()) == 10
    if trace is None:
        trace = new
        (packet/"behavior.trace").write_bytes(read("trace"))
    assert trace == new
    proof.append(v)
    work.append(read("work").decode())
    table = {k:json.loads(n) for k,n in re.findall(r"^WORK ([a-z-]+) (.+)$",work[-1],re.M)}
    assert set(table) == {"matched-loaded", "matched-live-stress", "matched-empty",
                          "fallback-loaded", "fallback-live-stress", "fallback-empty"}
    assert all(len(r) == 2 and all(type(x) is int and x >= 0 for x in r) for r in table.values())
    values[tier, arm] = table
for tier in tiers:
    before, after = (values[tier, a] for a in arms)
    assert before["matched-loaded"] == before["fallback-loaded"] == after["fallback-loaded"] == [108,8504]
    assert before["matched-live-stress"] == before["fallback-live-stress"] == after["fallback-live-stress"] == [200,13569]
    assert all(after[k] == [0,0] for k in after if k.startswith("matched-"))
    assert all(before[k] == [0,0] for k in before if k.endswith("-empty"))
    assert after["fallback-empty"] == [0,0]
lines = [l for l in log.read_text().splitlines() if l.startswith(("PASS ","FENCE "))]
assert len([l for l in lines if l.startswith("PASS fresh")]) == 4
assert lines[-1] == "PASS exact scripted scheduling and results; no real app startup/backend/native/UI/terminal/network execution"
(packet/"cargo-provenance.json").write_text(json.dumps(proof,sort_keys=True,indent=2)+"\n")
(packet/"work.log").write_text("Fields: allocation/reallocation requests and aggregate requested bytes. "
                              "Exact fallback-clone expression on prebuilt source layouts; no app start or allocator RSS.\n\n"
                              +"\n".join(work))
(packet/"evidence.log").write_text("\n".join(lines)+"\n")
print("PASS four admitted arms, identical full scripted records",sha(trace))
