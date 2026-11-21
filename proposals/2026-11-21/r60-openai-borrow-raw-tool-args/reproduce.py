#!/usr/bin/env python3
"""Compare actual OpenAI request rendering with read-only locked Cargo artifacts."""
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
PROBE = "r60_probe::allocation_case"
FIXTURES = ("no-calls", "raw-small", "raw-large", "raw-malformed", "decoded-small",
            "decoded-large", "freeform-small", "freeform-large", "freeform-invalid", "mixed-results")
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
            form,"--cfg","r60_probe", "-C",opt,"-C","strip=debuginfo",
            *data["rustflags"], "-L",f"dependency={artifacts/'deps'}",
            *dep_args,src/"lib.rs","-o",dest],
           env={**os.environ,"CARGO_PKG_VERSION":"0.1.0-alpha.2"}, cwd=src,check=True)
    if mode == "ordered":
        for group in ("adapters::openai::request_tests", "adapters::openai::tests::request_",
                      "adapters::openai::tests::malformed_function_arguments_are_preserved_for_failed_result_replay"):
            sp.run([dest,group,"--test-threads=1"],check=True)

def verify_body(raw,case,mode):
    if case=="freeform-invalid":
        assert raw == b"ERROR: freeform tool call 'fixture_note' requires string arg 'input'"
        return
    value = json.loads(raw)
    assert value["input"][0]["content"] == [{"type":"input_text","text":"format a note"}]
    items = value["input"][1:]
    if case=="no-calls":
        assert not items
        return
    large = "aб🦀" * 20_000
    small = " keep this \nстрока 🦀 "
    raw_small = ' \n{ "z": "привет", "a": 1 }\t'
    if case=="mixed-results":
        assert len(items)==6
        assert [i["type"] for i in items] == ["function_call","function_call_output",
            "function_call","function_call_output","custom_tool_call","custom_tool_call_output"]
        assert [i["call_id"] for i in items] == ["raw","raw","json","json","note","note"]
        assert all(i["output"]=="formatted" for i in items[1::2])
        pairs = list(zip(items[::2], ("raw-small", "decoded-small", "freeform-small")))
    else:
        assert len(items)==1
        pairs = [(items[0],case)]
    for item, kind in pairs:
        if kind.startswith("raw"):
            expected = {"raw-small":raw_small, "raw-large":f' \n{{"input":"{large}"}}\t',
                        "raw-malformed":"{not JSON 🦀\n"}[kind]
        if kind.startswith("decoded"):
            expected = json.dumps({"z":[1,False],"a":large if kind.endswith("large") else small},
                                  sort_keys=mode=="sorted",ensure_ascii=False,separators=(",",":"))
        freeform = kind.startswith("freeform")
        if freeform:
            expected = large if kind.endswith("large") else small
        key = "input" if freeform else "arguments"
        ordered = ("type","call_id","name",key)
        assert tuple(item) == (ordered if mode=="ordered" else tuple(sorted(ordered)))
        assert item[key]==expected
        assert item["type"]==("custom_tool_call" if freeform else "function_call")

with tempfile.TemporaryDirectory(prefix="r60-model-pack-") as work:
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
        with (src/"adapters/openai.rs").open("a") as f:
            f.write("""
#[cfg(r60_probe)]
pub(crate) fn r60_render(request: &CanonicalModelRequest) -> Result<Value> {
    static PROFILE: std::sync::OnceLock<OpenAiModelProfile> = std::sync::OnceLock::new();
    let profile = PROFILE.get_or_init(|| {
        OpenAiModelProfile::from_provider_config(&serde_json::json!({
            "capabilities": {
                "supports_parallel_tool_calls": true,
                "supports_json_schema": true,
                "supports_reasoning_config": true
            }
        })).expect("fixed benchmark profile")
    });
    request::to_openai_request_with_cache(request, &OpenAiPromptCacheConfig::default(), profile)
}
""")
        for mode in SPECS:
            print(f"--- building {arm}/{mode}",flush=True)
            build(src,mode,temp/f"{arm}-{mode}")
    for mode in SPECS:
        for case in FIXTURES:
            reference = None
            records = {arm: [] for arm in ARMS}
            for lap in range(3):
                for arm in (ARMS if lap%2==0 else ARMS[::-1]):
                    out = temp/"wire.json"
                    env = {**os.environ,"R60_CASE":case, "R60_WIRE":str(out)}
                    cmd = [temp/f"{arm}-{mode}"]
                    if mode == "ordered":
                        cmd += [PROBE,"--exact","--ignored","--nocapture","--test-threads=1"]
                    log = sp.check_output(cmd,env=env,text=True)
                    raw = out.read_bytes()
                    if reference is None:
                        reference = raw
                        verify_body(raw, case, mode)
                    assert raw == reference,(mode,case,arm)
                    meter = re.search(r"R60 (\d+) (\d+) (\d+)",log)
                    assert meter,log
                    records[arm].append(tuple(map(int,meter.groups())))
            print(f"{mode}/{case}: byte-exact; SHA256 {hashlib.sha256(reference).hexdigest()}")
            for arm, stats in records.items():
                print(f" {arm}: requested bytes / calls / logical peak {stats}; median "
                      f"{tuple(statistics.median(x) for x in zip(*stats))}")
