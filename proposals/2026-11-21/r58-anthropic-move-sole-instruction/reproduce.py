#!/usr/bin/env python3
"""Compare actual Anthropic request rendering with read-only locked Cargo artifacts."""
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
parser.add_argument("repo", type=Path, help="checkout containing the exact stock commit")
parser.add_argument("target", type=Path, help="existing immutable locked Cargo target")
args = parser.parse_args()
ARMS = ("base", "candidate")
PROBE = "r58_probe::allocation_case"
FIXTURES = {
    "canonical-small": " Be precise 🦀 ",
    "canonical-large": "aб🦀" * 20_000,
    "legacy-large": "aб🦀" * 20_000,
    "both-small": " high \n\n tied\n\n\nlow\n\n\n\n legacy \t\n\n",
    "both-large": "setup" * 10_000 + "\n\n" + "aб🦀" * 14_000,
    "all-empty": None,
    "pair-empty-legacy": "\n\n",
}
SPECS = {
    "sorted": ("release", "lib", "opt-level=3", "--crate-type=bin"),
    "ordered": ("debug", "test-lib", "opt-level=0", "--test"),
}
def needs(artifacts, selector, field):
    items = []
    for value in (artifacts/".fingerprint").glob(f"*/{field}"):
        if value.read_text().strip() == selector.to_bytes(8,"little").hex():
            items.append(value)
    [artifact] = items
    return artifact

def build(src, mode, dest):
    profile, task, opt, form = SPECS[mode]
    artifacts = args.target.resolve()/profile
    [fingerprint] = (artifacts/".fingerprint").glob(f"model-pack-*/{task}-model_pack.json")
    data = json.loads(fingerprint.read_text())
    dep_args = []
    for _, name, _, signature in data["deps"]:
        artifact = needs(artifacts, signature, f"lib-{name}")
        dep_hash = artifact.parent.name.split("-")[-1]
        if name == "serde_json":
            features = json.loads(json.loads(artifact.with_suffix(".json").read_text())["features"])
            assert ("preserve_order" in features) == (mode == "ordered"), features
            print(f"{mode} serde_json cargo artifact {artifact.parent.name} {features}")
        matches = [(artifacts/"deps"/f"lib{name}-{dep_hash}{extension}") for extension in (".rlib",".so")]
        [lib] = [m for m in matches if m.is_file()]
        if name == "ring":
            ring = json.loads(artifact.with_suffix(".json").read_text())
            [native_hash] = [v for _, dependency, _, v in ring["deps"] if dependency == "build_script_build"]
            build_script = needs(artifacts, native_hash, "run-build-script-build-script-build")
            native = artifacts/"build"/build_script.parent.name/"out"
            dep_args += ["-L", f"native={native}"]
        dep_args += ["--extern", f"{name}={lib}"]
    sp.run(["rustc","--edition","2024","--crate-name","model_pack",
            form,"--cfg","r58_probe", "-C",opt,"-C","strip=debuginfo",
            *data["rustflags"], "-L",f"dependency={artifacts/'deps'}",
            *dep_args,src/"lib.rs","-o",dest],
           env={**os.environ,"CARGO_PKG_VERSION":"0.1.0-alpha.2"}, cwd=src,check=True)
    if mode == "ordered":
        for group in ("adapters::anthropic::request_tests", "adapters::openai::request_tests"):
            sp.run([dest,group,"--test-threads=1"],check=True)

def verify_body(raw,expected,cache):
    value = json.loads(raw)
    assert value["messages"] == [{"role":"user", "content":[{"type": "text", "text": "question"}]}]
    if expected is None:
        assert "system" not in value
    elif cache:
        assert value["system"] == [{"type":"text", "text":expected,
                                    "cache_control":{"type":"ephemeral","ttl":"1h"}}]
    else:
        assert value["system"] == expected

with tempfile.TemporaryDirectory(prefix="r58-model-pack-") as work:
    temp = Path(work)
    source_dir = Path("model/model-pack/src")
    for arm in ARMS:
        tree = temp/arm
        sp.run(["git","clone","--no-checkout","--shared","-q",args.repo.resolve(),tree], check=True)
        sp.run(["git","-C",tree,"checkout","--detach","-q",BASE],check=True)
        if arm == "candidate":
            sp.run(["git","-C",tree,"apply","--check",HERE/"candidate.patch"],check=True)
            sp.run(["git","-C",tree,"apply",HERE/"candidate.patch"],check=True)
        src = tree/source_dir
        with (src/"lib.rs").open("a") as f:
            f.write("\n"+(HERE/"probe.rs").read_text())
        with (src/"adapters/anthropic.rs").open("a") as f:
            f.write("""
#[cfg(r58_probe)]
pub(crate) fn r58_render(request: &CanonicalModelRequest) -> Result<Value> {
    let cache = AnthropicPromptCacheConfig { enabled: true, ttl: Some("1h".into()) };
    to_anthropic_request_with_cache(request, &cache)
}
""")
        for mode in SPECS:
            print(f"--- building {arm}/{mode}",flush=True)
            build(src,mode,temp/f"{arm}-{mode}")
    for mode in SPECS:
        for case, expected in FIXTURES.items():
            for cache in (False, True):
                reference = None
                records = {arm: [] for arm in ARMS}
                for lap in range(3):
                    for arm in (ARMS if lap%2==0 else ARMS[::-1]):
                        out = temp/"wire.json"
                        env = {**os.environ,"R58_CASE":case, "R58_WIRE":str(out)}
                        env.pop("R58_CACHE",None)
                        if cache:
                            env["R58_CACHE"] = "1"
                        cmd = [temp/f"{arm}-{mode}"]
                        if mode == "ordered":
                            cmd += [PROBE,"--exact","--ignored","--nocapture","--test-threads=1"]
                        log = sp.check_output(cmd,env=env,text=True)
                        raw = out.read_bytes()
                        if reference is None:
                            reference = raw
                            verify_body(raw, expected, cache)
                        assert raw == reference,(mode,case,cache,arm)
                        meter = re.search(r"R58 (\d+) (\d+) (\d+)",log)
                        assert meter,log
                        records[arm].append(tuple(map(int,meter.groups())))
                print(f"{mode}/{case}/cache={cache}: byte-exact; SHA256 {hashlib.sha256(reference).hexdigest()}")
                for arm, stats in records.items():
                    print(f" {arm}: requested bytes / calls / logical peak {stats}; median "
                          f"{tuple(statistics.median(x) for x in zip(*stats))}")
