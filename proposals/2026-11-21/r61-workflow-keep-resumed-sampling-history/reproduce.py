#!/usr/bin/env python3
"""Pair exact prepared sampling requests with already built locked dependency graphs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess as sp
import tempfile

BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("repo", type=Path)
parser.add_argument("target", type=Path, help="read-only prebuilt locked Cargo target")
args = parser.parse_args()
ARMS = ("base", "candidate")
PROBE = "tests::r61_probe::allocation_case"
CASES = ("first-empty","first-small","first-large","first-restored",
         "pre-unchanged","pre-replacement","pre-error")
SPECS = {
    "sorted": ("release", "test-lib", "opt-level=3"),
    "ordered": ("debug", "test-lib", "opt-level=0"),
}

def build(src, mode, dest):
    profile, task, opt = SPECS[mode]
    artifacts = args.target.resolve()/profile
    [fingerprint] = (artifacts/".fingerprint").glob(f"coding-workflow-*/{task}-coding_workflow.json")
    data = json.loads(fingerprint.read_text())
    dep_args = []
    for _, name, _, signature in data["deps"]:
        tokens = signature.to_bytes(8,"little").hex()
        [artifact] = [p for p in (artifacts/".fingerprint").glob(f"*/lib-{name}")
                      if p.read_text().strip()==tokens]
        dep_hash = artifact.parent.name.split("-")[-1]
        if name == "serde_json":
            features = json.loads(json.loads(artifact.with_suffix(".json").read_text())["features"])
            assert ("preserve_order" in features) == (mode == "ordered"), features
            print(f"{mode} serde_json cargo artifact {artifact.parent.name} {features}")
        lib = artifacts/"deps"/f"lib{name}-{dep_hash}.rlib"
        assert lib.is_file(),lib
        dep_args += ["--extern", f"{name}={lib}"]
    sp.run(["rustc","--edition","2024","--crate-name","coding_workflow","--test",
            "-C",opt,"-C","strip=debuginfo",*data["rustflags"],
            "-L",f"dependency={artifacts/'deps'}",*dep_args,src/"lib.rs","-o",dest],
           cwd=src,check=True)
    sp.run([dest,"--skip",PROBE,"--test-threads=1"],check=True)

def independently_check(wire, case):
    value = json.loads(wire)
    if case == "pre-error":
        assert value == "fixture preparation unavailable", value
        return
    request, compaction, target = value
    def identifier(i):
        return f"00000000-0000-7000-8000-{i:012x}"
    msgids = [m["id"] for m in request["messages"]]
    assert request["cache"]["routing_key"] == "proteus:execution:"+identifier(65535)
    if case.startswith("first-"):
        assert compaction is None and target is None
        count = {"first-empty":0,"first-small":3,"first-large":96,"first-restored":3}[case]
        assert msgids == [*(identifier(i) for i in range(1,count+1)),
                          *([identifier(1000)] if count else [])]
        assert request["metadata"]["compaction_trigger_tokens"]==4200
        if case=="first-restored":
            assert request["metadata"]["model/input_token_estimates"]["parts"] == [
                {"part_id":identifier(65537),"tokens":123}]
    elif case == "pre-unchanged":
        assert msgids == [*(identifier(i) for i in range(1,4)),identifier(1000)]
        assert compaction["changed"] is False and target is None
    else:
        assert msgids == [identifier(1001),identifier(1000)]
        assert compaction["changed"] is True and target["revision"]==7
        assert request["metadata"]["compaction_trigger_tokens"]==8100

with tempfile.TemporaryDirectory(prefix="r61-workflow-") as work:
    temp = Path(work)
    for arm in ARMS:
        tree = temp/arm
        sp.run(["git","clone","--no-checkout","--shared","-q",args.repo.resolve(),tree],check=True)
        sp.run(["git","-C",tree,"checkout","--detach","-q",BASE],check=True)
        if arm=="candidate":
            sp.run(["git","-C",tree,"apply","--check",HERE/"candidate.patch"],check=True)
            sp.run(["git","-C",tree,"apply",HERE/"candidate.patch"],check=True)
        src = tree/"workflow/coding-workflow/src"
        with (src/"tests.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r61_probe;\n")
        (src/"tests/r61_probe.rs").write_bytes((HERE/"probe.rs").read_bytes())
        for mode in SPECS:
            print(f"--- building {arm}/{mode}",flush=True)
            build(src,mode,temp/f"{arm}-{mode}")
    for mode in SPECS:
        for case in CASES:
            reference=None
            records={arm:[] for arm in ARMS}
            for lap in range(3):
                for arm in (ARMS if lap%2==0 else ARMS[::-1]):
                    out=temp/"wire.json"
                    env={**os.environ,"R61_CASE":case,"R61_WIRE":str(out)}
                    log=sp.check_output([temp/f"{arm}-{mode}",PROBE,"--exact","--ignored",
                                         "--nocapture","--test-threads=1"],env=env,text=True)
                    wire=out.read_bytes()
                    if reference is None:
                        reference=wire
                        independently_check(wire,case)
                    assert wire==reference,(case,mode,arm)
                    meter=re.search(r"R61 (\d+) (\d+) (\d+)",log)
                    assert meter,log
                    records[arm].append(tuple(map(int,meter.groups())))
            print(f"{mode}/{case}: byte-exact; SHA256 {hashlib.sha256(reference).hexdigest()}")
            for arm, stats in records.items():
                print(f" {arm}: requested bytes / calls / logical peak {stats}; median "
                      f"{tuple(statistics.median(x) for x in zip(*stats))}")
