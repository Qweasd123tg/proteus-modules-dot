#!/usr/bin/env python3
"""Pair exact rendered skill catalog context with already built locked dependency graphs."""
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
PROBE = "r63_probe::allocation_case"
CASES = ("empty","plain","mixed","catalog","escape-heavy","nonutf8-location")
SPECS = {
    "sorted": ("release", "test-lib", "opt-level=3"),
    "ordered": ("debug", "test-lib", "opt-level=0"),
}

def build(src, mode, dest):
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
    sp.run([dest,"--skip",PROBE,"--test-threads=1"],check=True)

def independently_check(wire, case):
    [chunk] = json.loads(wire)
    descriptions = {
        "plain":"Check formatting and tests",
        "mixed":'\tCheck  <diff>\n&  "тесты"\u2003\'🦀\' &amp;\r\n',
        "catalog":"Inspect project notes  & test\nformats 🦀\u00a0"*7,
        "escape-heavy":'& < > " \' 🦀\t'*60,
        "nonutf8-location":"Check formatting and tests",
    }
    count = {"empty":0,"plain":1,"mixed":4,"catalog":64,"escape-heavy":16,"nonutf8-location":1}[case]
    def entities(text):
        for raw, escaped in (("&","&amp;"),("<","&lt;"),(">","&gt;"),('"',"&quot;"),("'","&apos;")):
            text=text.replace(raw, escaped)
        return text
    expected = "<available_skills>\n"
    for i in range(count):
        name=f"review-{i:02}"
        location = (f"fixture/{name}/SKILL.md" if case=="plain" else
                    "fixture/bad-� & notes/SKILL.md" if case=="nonutf8-location" else
                    f"fixture/{name} & notes/SKILL.md")
        description = entities(" ".join(descriptions[case].split()))
        expected += (
            f"<skill>\n<name>{name}</name>\n<description>{description}</description>\n"
            f"<location>{entities(location)}</location>\n</skill>\n")
    expected += "</available_skills>"
    assert chunk["content"]==expected,(case,chunk["content"][:500])
    assert chunk["source"]=="repo_aware:skills"
    assert chunk["metadata"]["provider"]=="skills"
    assert chunk["metadata"]["skill_count"]==count

with tempfile.TemporaryDirectory(prefix="r63-skill-pack-") as work:
    temp = Path(work)
    for arm in ARMS:
        tree = temp/arm
        sp.run(["git","clone","--no-checkout","--shared","-q",args.repo.resolve(),tree],check=True)
        sp.run(["git","-C",tree,"checkout","--detach","-q",BASE],check=True)
        if arm=="candidate":
            sp.run(["git","-C",tree,"apply","--check",HERE/"candidate.patch"],check=True)
            sp.run(["git","-C",tree,"apply",HERE/"candidate.patch"],check=True)
        src = tree/"tool/skill-pack/src"
        with (src/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r63_probe;\n")
        (src/"r63_probe.rs").write_bytes((HERE/"probe.rs").read_bytes())
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
                    env={**os.environ,"R63_CASE":case,"R63_WIRE":str(out)}
                    log=sp.check_output([temp/f"{arm}-{mode}",PROBE,"--exact","--ignored",
                                         "--nocapture","--test-threads=1"],env=env,text=True)
                    wire=out.read_bytes()
                    if reference is None:
                        reference=wire
                        independently_check(wire,case)
                    assert wire==reference,(case,mode,arm)
                    meter=re.search(r"R63 (\d+) (\d+) (\d+)",log)
                    assert meter,log
                    records[arm].append(tuple(map(int,meter.groups())))
            print(f"{mode}/{case}: byte-exact; SHA256 {hashlib.sha256(reference).hexdigest()}")
            for arm, stats in records.items():
                print(f" {arm}: requested bytes / calls / logical peak {stats}; median "
                      f"{tuple(statistics.median(x) for x in zip(*stats))}")
