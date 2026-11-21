#!/usr/bin/env python3
"""Pair complete Context Pack replies and provider requests with already built locked dependency graphs."""
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
parser.add_argument("--composed-only", type=Path, help="test an already-composed checked source tree")
args = parser.parse_args()
ARMS = ("base", "candidate")
PROBE = "r66_probe::allocation_case"
CASES = ("simple-null","simple-empty","simple-custom","repo-small",
         "repo-rich","codex-rich","repo-unknown","codex-bad-type")
SPECS = {
    "sorted": ("release", "test-lib", "opt-level=3"),
    "ordered": ("debug", "test-lib", "opt-level=0"),
}

def build(src, mode, dest):
    profile, task, opt = SPECS[mode]
    artifacts = args.target.resolve()/profile
    [fingerprint] = (artifacts/".fingerprint").glob(f"context-pack-*/{task}-context_pack.json")
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
    sp.run(["rustc","--edition","2024","--crate-name","context_pack","--test",
            "-C",opt,"-C","strip=debuginfo",*data["rustflags"],
            "-L",f"dependency={artifacts/'deps'}",*dep_args,src/"lib.rs","-o",dest],
           cwd=src,check=True)
    sp.run([dest,"--skip",PROBE,"--test-threads=1"],check=True)

def independently_check(wire, case):
    frame=json.loads(wire)
    if case in ("repo-unknown","codex-bad-type"):
        expected = {"repo-unknown":"unknown field `bogus`",
                    "codex-bad-type":"invalid type: boolean `true`, expected a sequence"}[case]
        assert frame["body"].startswith("ERROR: ") and expected in frame["body"],frame
        assert frame["trace"]==[],frame
        return
    order = {
        "simple-null":[], "simple-empty":[],
        "simple-custom":["fixture_memory","fixture_search"],
        "repo-small":["fixture_first"],
        "repo-rich":["fixture_first","fixture_second"],
        "codex-rich":["fixture_first","fixture_second"],
    }[case]
    assert [row[0] for row in frame["trace"]]==order
    for provider,raw in frame["trace"]:
        callback=json.loads(raw)
        assert callback["provider_id"]==provider
        assert callback["task"]=={"text":"inspect synthetic note 🦀","cwd":"fixture-root"}
        if provider=="fixture_search":
            assert callback["metadata"]["max_results"]==7
        elif provider not in ("fixture_memory",):
            assert callback["metadata"] is None
    body=json.loads(frame["body"])
    assert len(body["chunks"])==len(order)+(0 if case=="codex-rich" else 1),body
    assert sum(row["content"]=="Result for note." for row in body["chunks"])==len(order)

if args.composed_only is not None:
    with tempfile.TemporaryDirectory(prefix="r66-composed-") as work:
        print("--- building composed/ordered",flush=True)
        build(args.composed_only.resolve()/"context/context-pack/src",
              "ordered",Path(work)/"composed")
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="r66-context-pack-") as work:
    temp = Path(work)
    for arm in ARMS:
        tree = temp/arm
        sp.run(["git","clone","--no-checkout","--shared","-q",args.repo.resolve(),tree],check=True)
        sp.run(["git","-C",tree,"checkout","--detach","-q",BASE],check=True)
        if arm=="candidate":
            sp.run(["git","-C",tree,"apply","--check",HERE/"candidate.patch"],check=True)
            sp.run(["git","-C",tree,"apply",HERE/"candidate.patch"],check=True)
        src = tree/"context/context-pack/src"
        with (src/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r66_probe;\n")
        (src/"r66_probe.rs").write_bytes((HERE/"probe.rs").read_bytes())
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
                    env={**os.environ,"R66_CASE":case,"R66_WIRE":str(out)}
                    log=sp.check_output([temp/f"{arm}-{mode}",PROBE,"--exact","--ignored",
                                         "--nocapture","--test-threads=1"],env=env,text=True)
                    wire=out.read_bytes()
                    if reference is None:
                        reference=wire
                        independently_check(wire,case)
                    assert wire==reference,(case,mode,arm)
                    meter=re.search(r"R66 (\d+) (\d+) (\d+)",log)
                    assert meter,log
                    records[arm].append(tuple(map(int,meter.groups())))
            print(f"{mode}/{case}: byte-exact; SHA256 {hashlib.sha256(reference).hexdigest()}")
            for arm, stats in records.items():
                print(f" {arm}: requested bytes / calls / logical peak {stats}; median "
                      f"{tuple(statistics.median(x) for x in zip(*stats))}")
