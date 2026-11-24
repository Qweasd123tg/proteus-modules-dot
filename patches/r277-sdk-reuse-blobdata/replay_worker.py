#!/usr/bin/env python3
"""Replay the actual worker builds and upstream process tests from exact local inputs."""
from argparse import ArgumentParser
import json
import os
from pathlib import Path
import shutil
import subprocess
from worker_inputs import HERE, cargo, git_blob, need, sha, stage_native_inputs

REL = Path("crates/proteus-module-sdk/src/session_storage.rs")
BLOBS = ("a9ad263f69e79121395c640b7a8fee23f1dc32d0", "6b0b56d4a4a92c0a480619dd7c3b2731845ff444")
PATCH = "144882dc7b9e0a3600dfea285f924b1778c3e490ee1ad475a957d3d835c94082"
COMPONENT = Path("components/session-storage-module")
BIN = "proteus-session-storage-module"

def apply(candidate, patch):
    need(sha(patch.read_bytes()) == PATCH, "exact source patch SHA-256")
    def git(*args):
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "GIT_CONFIG_GLOBAL": "/dev/null",
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CEILING_DIRECTORIES": str(candidate.parent)}
        return subprocess.check_output(["git", "apply", "--whitespace=error-all", *args, patch],
                                       cwd=candidate, env=env, text=True)
    need(git("--numstat").strip().split("\t") == ["38", "1", REL.as_posix()], "only actual SDK path")
    for i, expected in enumerate((*BLOBS, *BLOBS)):
        if i:
            opts = ["--reverse"] if i == 2 else []
            git("--check", *opts)
            git(*opts)
        need(git_blob((candidate/REL).read_bytes()) == expected, "exact pre/post SDK blob")

def pick(raw, target, tests=False):
    artifacts = [e for l in raw.splitlines() if l.startswith("{") and
        (e:=json.loads(l)).get("reason")=="compiler-artifact" and e["target"]["name"]==target
        and e["profile"]["test"]==tests]
    need(len(artifacts)==1, f"exact artifact {target}")
    return artifacts[0]

def verify_profile(work, tools, mode, jobs):
    args = ["--features", "serde_json/preserve_order"] if mode == "preserve_order" else []
    records = {}
    for arm in ("stock", "candidate"):
        root=work/"native"/arm
        tag=f"{arm}-{mode}"
        bef=(root/REL).read_bytes()
        need(git_blob(bef)==BLOBS[arm=="candidate"], "verified SDK source before compile")
        cargo(work, tools, arm, "clean", "--release", "-p", BIN, "-p", "proteus-module-sdk", capture=True)
        raw=cargo(work,tools,arm,"build","--release","-j",jobs,"-p",BIN,"--bin",BIN,
                  "--message-format=json",*args,capture=True)
        (work/f"{tag}-compiler.jsonl").write_text(raw)
        sdk,bin=(pick(raw,target) for target in ("proteus_module_sdk", BIN))
        serde=pick(raw,"serde_json")
        need(not sdk["fresh"] and not bin["fresh"],"fresh actual SDK and worker")
        need(Path(sdk["manifest_path"])==root/REL.parents[1]/"Cargo.toml", "exact SDK")
        need(Path(sdk["target"]["src_path"])==root/REL.parent/"lib.rs", "exact SDK entry")
        need(Path(bin["manifest_path"])==root/COMPONENT/"Cargo.toml", "exact worker")
        need(Path(bin["target"]["src_path"])==root/COMPONENT/"src/main.rs", "exact worker entry")
        need(("preserve_order" in serde["features"])==bool(args), "actual compiled serde_json mode")
        native=Path(bin["executable"])
        frozen=work/f"{tag}-worker"
        shutil.copy2(native,frozen)
        need((root/REL).read_bytes()==bef, "unchanged SDK during build")
        raw=cargo(work,tools,arm,"test","--release","-j",jobs,"-p",BIN,"--test","process","--no-run",
                  "--message-format=json",*args,capture=True)
        (work/f"{tag}-process-compiler.jsonl").write_text(raw)
        test=pick(raw,"process",True)
        need(Path(test["target"]["src_path"])==root/COMPONENT/"tests/process.rs", "actual upstream process tests")
        process_env={"PATH":"/usr/bin:/bin","LC_ALL":"C.UTF-8",
                     "HOME":str(work/"cargo-home"),"TMPDIR":str(work/"tmp")}
        p=subprocess.run([test["executable"],"--test-threads=1","--nocapture"],cwd=work,
                         env=process_env,text=True,check=True,capture_output=True,timeout=120)
        (work/f"{tag}-process.log").write_text(p.stdout+p.stderr)
        need("test result: ok. 2 passed; 0 failed;" in p.stdout, "exact process tests passed")
        digest=sha(frozen.read_bytes())
        need(sha(native.read_bytes())==digest, "process suite executed the retained worker")
        records[arm]={"worker_sha256":digest,"serde_features":serde["features"],"upstream_process_tests":2}
    need(records["stock"]["worker_sha256"]!=records["candidate"]["worker_sha256"],"distinct product artifacts")
    return records

def main():
    p=ArgumentParser(description=__doc__)
    for x in ("modules","core","work","toolchain-bin"):
        p.add_argument("--"+x, type=Path,required=True)
    p.add_argument("--archives",type=Path,action="append",required=True)
    p.add_argument("--patch",type=Path,default=HERE/"source.patch")
    p.add_argument("--jobs",default="3")
    p.add_argument("--mode",action="append",choices=("default","preserve_order"))
    a=p.parse_args()
    work,tools=a.work.resolve(),a.toolchain_bin.resolve()
    _,candidate=stage_native_inputs(a.modules,a.core,work,tools,a.archives)
    apply(candidate,a.patch.resolve())
    modes=a.mode or ["default","preserve_order"]
    need(len(set(modes))==len(modes),"unique profile modes")
    result={mode:verify_profile(work,tools,mode,a.jobs) for mode in modes}
    (work/"native-compiler-evidence.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    main()
