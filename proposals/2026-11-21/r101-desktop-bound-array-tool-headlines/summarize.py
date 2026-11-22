"""Seal fresh Cargo evidence, complete per-mode byte equality, and ordinary work checks."""
import hashlib
import json
from pathlib import Path
import re
import sys

raw, out = map(Path, sys.argv[1:])
arms = ("pin-baseline", "pin-candidate", "after423-baseline", "after423-candidate")
modes = ("sorted", "ordered")
provenance, parity, work_log, examples = [], [], [], []

def sha(b):
    return hashlib.sha256(b).hexdigest()

for mode in modes:
    ref = None
    work = {}
    for arm in arms:
        stem = raw / f"{arm}-{mode}"
        def named(suffix):
            return Path(f"{stem}.{suffix}")
        attestation = json.loads(named("provenance").read_text())
        expected_arm = arm.replace("-", "/") + "/" + mode
        assert attestation["arm"] == expected_arm and not attestation["fresh"]
        assert attestation["sha256_before"] == attestation["sha256_after"]
        assert len(attestation["tests"]) == (12 if arm.startswith("pin-") else 14)
        full, wt = named("complete").read_bytes(), named("work").read_bytes()
        if ref is None:
            ref = full
        assert full == ref and attestation["complete_sha256"] == sha(full)
        assert attestation["complete_size"] == len(full)
        assert attestation["work_sha256"] == sha(wt)
        stats = {k: (int(c),int(b)) for k,c,b in re.findall(r"^WORK ([a-z0-9-]+): (\d+) (\d+)$", wt.decode(), re.M)}
        assert len(stats) == 7
        work[arm] = stats
        provenance.append(attestation)
        work_log.append(wt.decode())
    assert ref is not None and ref.count(b"\n") == 2043
    parity.append({"mode":mode,"matching_arms":4,"observation_records":2043,"bytes":len(ref),"sha256":sha(ref)})
    examples.extend(ref.splitlines()[:2])
    for tier in ("pin", "after423"):
        a,d = work[f"{tier}-baseline"], work[f"{tier}-candidate"]
        for n in (2,8,20):
            k = f"ordinary-{n}"
            assert all(new < old for old,new in zip(a[k],d[k]))
        for k in ("unicode-plural-bound","hidden-joined-tail"):
            assert all(new < old for old,new in zip(a[k],d[k]))
        k = "ordinary-custom-join"
        assert d[k][0] <= a[k][0] and d[k][1] < a[k][1]
        assert d["single-nonarray-control"] == a["single-nonarray-control"]
assert parity[0]["sha256"] != parity[1]["sha256"], "fallback insertion-order control must differ"
(out / "cargo-provenance.json").write_text(json.dumps(provenance,sort_keys=True,indent=2)+"\n")
(out / "parity.json").write_text(json.dumps(parity,sort_keys=True,indent=2)+"\n")
(out / "work.log").write_text("\n".join(work_log))
(out / "sample-observations.jsonl").write_bytes(b"\n".join(examples)+b"\n")
