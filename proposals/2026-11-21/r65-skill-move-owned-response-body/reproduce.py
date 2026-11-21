#!/usr/bin/env python3
"""Pair complete skill-tool responses with already built locked dependency graphs."""
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
parser.add_argument("--composed", type=Path, help="optional already-composed Modules source tree")
args = parser.parse_args()
ARMS = ("base", "candidate")
PROBE = "r65_probe::allocation_case"
CASES = ("small","large","empty","crlf","missing","disabled","bad-args","wrong-tool")
SPECS = {
    "sorted": ("release", "test-lib", "opt-level=3"),
    "ordered": ("debug", "test-lib", "opt-level=0"),
}

def build(src, mode, dest, fixture_home):
    profile, task, opt = SPECS[mode]
    artifacts = args.target.resolve()/profile
    [fingerprint] = (artifacts/".fingerprint").glob(f"skill-pack-*/{task}-skill_pack.json")
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
    sp.run(["rustc","--edition","2024","--crate-name","skill_pack","--test",
            "-C",opt,"-C","strip=debuginfo",*data["rustflags"],
            "-L",f"dependency={artifacts/'deps'}",*dep_args,src/"lib.rs","-o",dest],
           cwd=src,check=True)
    sp.run([dest,"--skip",PROBE,"--test-threads=1"],
           env={**os.environ,"PROTEUS_HOME":str(fixture_home)},check=True)

BODIES = {
    "review":"Inspect \"заметка\".\nKeep 🦀\tspaces.",
    "large":'Text "note" 🦀 paragraph.\tMore lines.\n'*3600,
    "blank":"\n  \t\n ",
    "windows":"Line one.\r\nСтрока два 🦀.\r\n",
}

def create_skills(workspace):
    (workspace/".git").mkdir(parents=True)
    for skill, body in BODIES.items():
        d=workspace/".proteus"/"skills"/skill
        d.mkdir(parents=True)
        header=f"---\nname: {skill}\ndescription: Fixture {skill}\n---\n\n"
        if skill=="windows":
            header=header.replace("\n","\r\n")
        (d/"SKILL.md").write_bytes((header+body).encode())

def independently_check(wire, case, mode, workspace):
    response=json.loads(wire)
    order=("call_id","ok","output","content","error","metadata")
    assert tuple(response)==(order if mode=="ordered" else tuple(sorted(order)))
    assert response["call_id"]=="call-ю" and response["content"]==[]
    if case in ("small","large","empty","crlf"):
        skill={"small":"review","large":"large","empty":"blank","crlf":"windows"}[case]
        assert response["ok"] is True and response["error"] is None
        assert response["output"]==BODIES[skill].strip()
        assert response["metadata"]=={
            "tool":"skill","name":skill,"description":f"Fixture {skill}","source":"project",
            "path":str(workspace/".proteus"/"skills"/skill/"SKILL.md"),
        }
        fields=("tool","name","description","path","source")
        assert tuple(response["metadata"])==(fields if mode=="ordered" else tuple(sorted(fields)))
    else:
        assert response["ok"] is False and response["output"]==""
        assert response["metadata"]=={"tool":"skill"}
        expected = {
            "missing":"skill 'missing' is not available in this workspace",
            "disabled":"skill 'review' is not available in this workspace",
            "bad-args":"invalid skill arguments: invalid type: integer `42`, expected a string",
            "wrong-tool":"unexpected tool name 'other'",
        }
        assert response["error"]==expected[case],response

with tempfile.TemporaryDirectory(prefix="r65-skill-pack-") as work:
    temp = Path(work)
    workspace=temp/"fixture"
    fixture_home=temp/"empty-home"
    create_skills(workspace)
    for arm in ARMS:
        tree = temp/arm
        sp.run(["git","clone","--no-checkout","--shared","-q",args.repo.resolve(),tree],check=True)
        sp.run(["git","-C",tree,"checkout","--detach","-q",BASE],check=True)
        if arm=="candidate":
            sp.run(["git","-C",tree,"apply","--check",HERE/"candidate.patch"],check=True)
            sp.run(["git","-C",tree,"apply",HERE/"candidate.patch"],check=True)
        src = tree/"tool/skill-pack/src"
        with (src/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r65_probe;\n")
        (src/"r65_probe.rs").write_bytes((HERE/"probe.rs").read_bytes())
        for mode in SPECS:
            print(f"--- building {arm}/{mode}",flush=True)
            build(src,mode,temp/f"{arm}-{mode}",fixture_home)
    for mode in SPECS:
        for case in CASES:
            reference=None
            records={arm:[] for arm in ARMS}
            for lap in range(3):
                for arm in (ARMS if lap%2==0 else ARMS[::-1]):
                    out=temp/"wire.json"
                    env={**os.environ,"R65_CASE":case,"R65_WIRE":str(out),
                         "R65_CWD":str(workspace),"PROTEUS_HOME":str(fixture_home)}
                    log=sp.check_output([temp/f"{arm}-{mode}",PROBE,"--exact","--ignored",
                                         "--nocapture","--test-threads=1"],env=env,text=True)
                    wire=out.read_bytes()
                    if reference is None:
                        reference=wire
                        independently_check(wire,case,mode,workspace)
                    assert wire==reference,(case,mode,arm)
                    meter=re.search(r"R65 (\d+) (\d+) (\d+)",log)
                    assert meter,log
                    records[arm].append(tuple(map(int,meter.groups())))
            print(f"{mode}/{case}: byte-exact; SHA256 {hashlib.sha256(reference).hexdigest()}")
            for arm, stats in records.items():
                print(f" {arm}: requested bytes / calls / logical peak {stats}; median "
                      f"{tuple(statistics.median(x) for x in zip(*stats))}")
    if args.composed is not None:
        print("--- building composed/ordered",flush=True)
        build(args.composed.resolve()/"tool/skill-pack/src","ordered",temp/"composed-ordered",fixture_home)
