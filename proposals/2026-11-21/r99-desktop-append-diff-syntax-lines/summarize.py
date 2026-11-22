"""Bind the four matching behaviors and eight separately selected executables."""
from pathlib import Path
import hashlib
import json
import re
import sys

raw, out = map(Path, sys.argv[1:])
tiers, arms = ("pin", "after421"), ("baseline", "candidate")
artifacts, units, work_summary = [], [], []
trace = None
for tier, expected_tests in zip(tiers, (13, 15)):
    work = {}
    for arm in arms:
        run = f"{tier}-{arm}"
        prefix = raw / run
        arm_name = f"{tier}/{arm}"
        for mode in ("unit", "probe"):
            row = json.loads(Path(f"{prefix}.{mode}.artifact").read_text().removeprefix("ARTIFACT "))
            assert row["arm"] == arm_name and row["mode"] == mode and not row["fresh"]
            assert row["executable_sha256_before"] == row["executable_sha256_after"]
            std = Path(f"{prefix}.{mode}.stdout").read_bytes()
            assert hashlib.sha256(std).hexdigest() == row["stdout_sha256"]
            it = [json.loads(x) for x in Path(f"{prefix}.{mode}.cargo-json").read_text().splitlines()]
            local = [x for x in it if x.get("reason") == "compiler-artifact"
                     and x["target"]["name"] == "proteus_diff"
                     and x["profile"]["test"] == (mode == "unit")]
            assert len(local) == 1 and not local[0]["fresh"]
            assert local[0]["manifest_path"].endswith(f"/{run}/crates/diff/Cargo.toml")
            assert local[0]["target"]["src_path"].endswith(f"/{run}/crates/diff/src/lib.rs")
            artifacts.append(row)
            if mode == "unit":
                status = next(s for s in std.decode().splitlines() if s.startswith("test result: ok."))
                assert status.startswith(f"test result: ok. {expected_tests} passed; 0 failed;")
                names = [s for s in std.decode().splitlines() if s.startswith("test ") and s.endswith(" ... ok")]
                assert len(names) == expected_tests
                units.extend((f"ARM {arm_name}", *names, re.sub(r"; finished in .*", "", status), ""))
            else:
                if trace is None:
                    trace = std
                assert trace == std
                lines = Path(f"{prefix}.probe.stderr").read_text().splitlines()
                assert lines[0] == "ARM " + arm_name
                assert all(re.fullmatch(r"WORK (append|side) [-a-z]+(?:/(?:true|false))?: [0-9]+ [0-9]+", l)
                           for l in lines[1:])
                stats = {key: tuple(map(int, val.split())) for key, val in
                         (l.removeprefix("WORK ").split(": ") for l in lines[1:])}
                assert len(lines) == 20 and len(stats) == 19
                work[arm] = stats
                work_summary.extend((*lines, ""))
    before, after = work["baseline"], work["candidate"]
    for key in before:
        if key.startswith("append"):
            assert after[key] == (0, 0)
            if key != "append blank":
                assert before[key][0] > 0
        if any(key.startswith(f"side {fixture}") for fixture in ("spaces", "sparse", "dense")):
            assert all(a < b for a, b in zip(after[key], before[key]))
    for fixture in ("empty-file", "metadata-only"):
        for old in ("true", "false"):
            assert before[f"side {fixture}/{old}"] == after[f"side {fixture}/{old}"]

assert len({(a["arm"], a["mode"]) for a in artifacts}) == 8
for mode in ("unit", "probe"):
    for tier in tiers:
        subset = [a for a in artifacts if a["arm"].startswith(tier + "/") and a["mode"] == mode]
        lhs, rhs = (a["inputs_sha256"] for a in subset)
        assert lhs.keys() == rhs.keys()
        assert {k for k in lhs if lhs[k] != rhs[k]} == {"src/syntax.rs"}
    parser = {a["arm"]: a["inputs_sha256"]["crates/diff/src/parse.rs"] for a in artifacts if a["mode"] == mode}
    assert parser["pin/baseline"] != parser["after421/baseline"]
(out / "behavior.trace").write_bytes(trace)
(out / "unit-results.log").write_text("\n".join(units) + "\n")
(out / "work.log").write_text("\n".join(work_summary) + "\n")
(out / "cargo-provenance.json").write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")
