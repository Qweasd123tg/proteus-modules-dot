#!/usr/bin/env python3
"""Pinned transmit-only badge ownership parity with per-arm fresh Cargo artifacts and measured scopes."""
import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess as sp
import tempfile

import fixtures

HERE = Path(__file__).resolve().parent
PIN = "892f627570369ed60d7205eb0d351c753ec4305f"
M150 = "60c98d197045c6d41d5f568cf44a106c0ec89d9aed13028ea6dd463568a24ac8"
OVERLAYS = [
    "3d85e07b31b7d7e14ccaa299e9fdafe5a2bb27aa95e858e97f3ebd9dacf981b9",
    "5a22007dbd5cc4a806aa40e2faccf0fa06ee2ea4bd45e38ba59634d9152c713a",
    "03cc1b188ad8266e8236ccf57af2eae1657a2559e34b8ce8aa4f9083ec2f05aa",
    "a5ff3516111d0bafef46504aeb40f8a9f147e701b96a80d0a79a136306844793",
    "fb66ec99b30c0fea837d538902b4d5528cb46d2e05ebedfdff4aed2c66fa197f",
]
SDK = "sdk/Cargo.toml"
MODE = "packages/mode/Cargo.toml"
MODEL = "packages/model/Cargo.toml"
CONTEXT = "packages/context/Cargo.toml"
PROBE = "host::tests::r79_badge_probe::meter_owned_badge_envelope"
PATCH_SHA = "d001261ce6023e500ac2643a5ff122793bebea2eb556b29d170d6c48d9813439"
TIER = "M150+394+395+397+399+402"
CHECK = "host::visual_preferences::tests::badge_frames_keep_hidden_default_null_and_context_error_order"
CASES = [
    ("default-empty",0,0,0), ("explicit-null",0,0,0), ("empty-spare",0,0,64),
    ("one-spare",1,18,64), ("nested-face-only",0,0,0), ("mode-ordinary",1,28,1),
    ("context-ordinary",2,50,2), ("quota-windows",32,90,32), ("large-owned",8,8192,8),
]
FLAGS = ["--release","--locked","--offline","-j1"]
PACKAGES = ("model","mode","context")
BINS = [item for name in PACKAGES for item in ("-p",f"extension-{name}")]
SCOPE = ["-p","proteus-extension",*BINS]
TEST_COUNTS = rb"^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;"


def hash_file(path):
    return sha256(path.read_bytes()).hexdigest()


def source_tree(path, omit_git=False):
    rows = []
    for entry in sorted(path.rglob("*")):
        rel = entry.relative_to(path)
        if omit_git and ".git" in rel.parts:
            continue
        if entry.is_symlink():
            rows.append([str(rel),"link",str(entry.readlink())])
        elif entry.is_file():
            rows.append([str(rel),"x" if entry.stat().st_mode & 0o111 else "-",hash_file(entry)])
    return sha256(json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def mode_model_wire(built, env, src, target):
    traces = {}
    for name, proof in built.items():
        folder = src / "packages" / name
        features = json.loads((folder/"extension.json").read_text())["required_features"]
        exe = target / next(iter(proof))
        traces[name] = (fixtures.context_badge(exe,features,env,folder) if name=="context"
                        else fixtures.ordinary(exe,name,features,env,folder))
    return traces


def split_probe(raw):
    rx=rb"^badge ([a-z-]+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$"
    meters=[(name.decode(),*map(int,rest)) for name,*rest in re.findall(rx,raw,re.M)]
    assert [record[:-3] for record in meters]==CASES,raw
    assert b"test result: ok. 1 passed; 0 failed; 0 ignored;" in raw,raw
    return meters


def control_sizes(a,b):
    for left,right in zip(a,b,strict=True):
        name,rows,width,input_capacity,output_capacity,calls,bytes_=left
        assert left[:-3]==right[:-3]
        cap1,calls1,bytes1=right[-3:]
        assert cap1<=output_capacity,(left,right)
        if name in {"explicit-null","empty-spare"}:
            assert calls1<=calls and bytes1<=bytes_,(left,right)
        else:
            assert calls1<calls and bytes1<bytes_,(left,right)
            if name in {"quota-windows","large-owned"}:
                assert bytes_-bytes1>=rows*width*2,(left,right)


def run(target, env, cwd, *cmd):
    if min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)<256*2**20:
        raise RuntimeError("disk stop floor")
    with tempfile.TemporaryFile(dir=HERE) as stdout, tempfile.TemporaryFile(dir=HERE) as stderr:
        with sp.Popen(cmd,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True) as child:
            try:
                while True:
                    try:
                        status = child.wait(timeout=2)
                        break
                    except sp.TimeoutExpired:
                        if min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)<256*2**20:
                            raise RuntimeError("disk stop floor")
            except BaseException:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except sp.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL)
                        child.wait()
                raise
        stdout.seek(0)
        stderr.seek(0)
        actual,error=stdout.read(),stderr.read()
    if status!=0:
        raise RuntimeError((cmd,status,actual.decode(errors="replace"),error.decode(errors="replace")))
    if min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)<256*2**20:
        raise RuntimeError("disk stop floor")
    return actual


def cargo_events(raw):
    rows = [json.loads(line) for line in raw.splitlines() if line.lstrip().startswith(b"{")]
    assert [r.get("success") for r in rows if r.get("reason")=="build-finished"]==[True]
    return [r for r in rows if r.get("reason")=="compiler-artifact"]


def select_artifact(events, src, manifest, source_path, name, kind, test, executable=True):
    target_file=src/source_path
    entries=[
        entry for entry in events if Path(entry["manifest_path"]).resolve()==src/manifest
        and entry["target"]["name"]==name and entry["target"]["kind"]==[kind]
        and Path(entry["target"]["src_path"]).resolve()==target_file
        and entry["profile"]["test"] is test
        and bool(entry["executable"])==executable
    ]
    assert len(entries)==1,(manifest,source_path,name,kind,test,len(entries))
    return entries[0]


def artifact_receipt(event, target, phase, manifest, input_hash, compiler):
    if event["executable"]:
        files = [event["executable"]]
    else:
        files = [name for name in event["filenames"] if name.endswith((".rlib",".rmeta"))]
        assert files and any(name.endswith(".rlib") for name in files),files
    fingerprints = {}
    for real in files:
        physical=Path(real).resolve(strict=True)
        assert physical.is_relative_to(target) and physical.is_file(),physical
        if event["executable"]:
            assert physical.stat().st_mode & 0o111,physical
        fingerprints[physical.relative_to(target).as_posix()]={"sha256":hash_file(physical),
                                                              "bytes":physical.stat().st_size}
    receipt={
        "phase":phase,"manifest":manifest,"name":event["target"]["name"],"kind":event["target"]["kind"],
        "test":event["profile"]["test"],"fresh":event["fresh"],"source_sha256":input_hash,
        "toolchain_sha256":compiler,"files":fingerprints,
    }
    print("artifact",json.dumps(receipt,sort_keys=True),flush=True)
    return fingerprints


def check_files(target, records):
    for path,signature in records.items():
        item=(target/path).resolve(strict=True)
        assert item.is_relative_to(target) and item.is_file()
        assert item.stat().st_size==signature["bytes"] and hash_file(item)==signature["sha256"],path


def assert_suite(raw,count):
    assert [tuple(map(int,row)) for row in re.findall(TEST_COUNTS,raw,re.M)]==[(count,0,0,0,0)],raw[-2000:]


def arm(root, tier, variant, args, target, env, toolchain):
    src=root/(tier+"-"+variant)
    patch=HERE/"source.patch"
    overlays=[]
    if tier=="base":
        sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",args.stock_git,src],check=True)
        run(target,env,src,"git","checkout","-q","--detach",PIN)
        assert run(target,env,src,"git","rev-parse","HEAD").decode().strip()==PIN
    else:
        shutil.copytree(args.m150_source,src,symlinks=True,copy_function=shutil.copy)
        assert source_tree(src)==M150
        for prior in args.prior:
            run(target,env,src,"git","apply","--check","--whitespace=error",prior)
            run(target,env,src,"git","apply","--whitespace=error",prior)
            overlays.append(hash_file(prior))
    run(target,env,src,"git","apply","--check","--whitespace=error",patch)
    if variant=="candidate":
        run(target,env,src,"git","apply","--whitespace=error",patch)
        run(target,env,src,"git","apply","--reverse","--check",patch)
        overlays.append(hash_file(patch))
    run(target,env,src,"cargo","fmt","-p","proteus-extension","--","--check")
    before = source_tree(src,omit_git=True)
    compiler = sha256(json.dumps(toolchain,sort_keys=True).encode()).hexdigest()
    print("arm",json.dumps({"tier":tier,"variant":variant,"source_sha256":before,"pin":PIN,
          "overlays":overlays,"lock_sha256":hash_file(src/"Cargo.lock"),"toolchain_sha256":compiler,
          "sdk_host_sha256":hash_file(src/"sdk/src/host.rs"),"profile":"release",
          "sdk_visual_tests_sha256":hash_file(src/"sdk/src/host/visual_preferences/tests.rs")},
          sort_keys=True),flush=True)
    counts=(60,10,4,3) if tier=="base" else (68,11,4,4)
    counts=(counts[0]+(variant=="candidate"),*counts[1:])

    events=cargo_events(run(target,env,src,"cargo","test","--no-run",*FLAGS,*SCOPE,"--message-format=json"))
    production = select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
    assert production["fresh"] is False,"SDK was not built freshly in this arm"
    sdk_files=artifact_receipt(production,target,tier+"/"+variant+"/unit-dependency",SDK,before,compiler)

    for (manifest,file,name,kind),size in zip([
        (SDK,"sdk/src/lib.rs","proteus_extension","lib"),
        (MODEL,"packages/model/src/main.rs","model","bin"),
        (MODE,"packages/mode/src/main.rs","mode","bin"),
        (CONTEXT,"packages/context/src/main.rs","context","bin"),
    ],counts,strict=True):
        event=select_artifact(events,src,manifest,file,name,kind,True)
        assert event["fresh"] is False,(manifest,"compiled test was cached")
        exe=artifact_receipt(event,target,tier+"/"+variant+"/unit-exe",manifest,before,compiler)
        check_files(target,exe)
        raw=run(target,env,(src/manifest).parent,target/next(iter(exe)))
        check_files(target,exe)
        assert_suite(raw,size)
        print("unit-pass",tier,variant,name,size,flush=True)
        if manifest==SDK and variant=="candidate":
            test_name=CHECK
            raw=run(target,env,(src/manifest).parent,target/next(iter(exe)),"--exact",test_name,"--test-threads=1")
            check_files(target,exe)
            assert [tuple(map(int,row)) for row in re.findall(TEST_COUNTS,raw,re.M)]==[(1,0,0,0,size-1)]
            assert f"test {test_name} ... ok".encode() in raw
            print("badge-pass",tier,variant,test_name,flush=True)
    check_files(target,sdk_files)
    assert_suite(run(target,env,src,"cargo","test","--doc",*FLAGS,"-p","proteus-extension"),1)
    check_files(target,sdk_files)
    print("doc-pass",tier,variant,"proteus_extension",1,flush=True)

    def linked_sdk(events, phase, source_hash):
        nonlocal sdk_files
        packaged=select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
        seen=artifact_receipt(packaged,target,tier+"/"+variant+"/"+phase,SDK,source_hash,compiler)
        if packaged["fresh"]:
            assert seen==sdk_files,"cached SDK does not match this arm's verified library"
        else:
            sdk_files=seen
        check_files(target,sdk_files)

    events=cargo_events(run(target,env,src,"cargo","build",*FLAGS,*BINS,"--bins","--message-format=json"))
    linked_sdk(events,"wire-dependency",before)
    built={}
    for file,name in [(MODEL,"model"),(MODE,"mode"),(CONTEXT,"context")]:
        event=select_artifact(events,src,file,f"packages/{name}/src/main.rs",name,"bin",False)
        assert event["fresh"] is False,(file,"wire binary was cached")
        built[name]=artifact_receipt(event,target,tier+"/"+variant+"/wire-exe",file,before,compiler)
        check_files(target,built[name])
    wire = mode_model_wire(built,env,src,target)
    for r in built.values():
        check_files(target,r)

    assert source_tree(src,omit_git=True)==before
    tests_file=src/"sdk/src/host/tests.rs"
    host=src/"sdk/src/host.rs"
    marker=b'\n#[path = "r79_badge_probe.rs"]\npub(super) mod r79_badge_probe;\n'
    assert marker not in tests_file.read_bytes()
    with tests_file.open("ab") as injected:
        injected.write(marker)
    hook=b'            self.sent.borrow_mut().push(message.clone());'
    body=host.read_bytes()
    assert body.count(hook)==1
    host.write_bytes(body.replace(hook,
        b'            if tests::r79_badge_probe::capture(message) { return; }\n'+hook,1))
    probe=src/"sdk/src/host/r79_badge_probe.rs"
    assert not probe.exists()
    shutil.copyfile(HERE/"probe.rs",probe)
    probe_source=source_tree(src,omit_git=True)
    print("probe-source",json.dumps({"tier":tier,"variant":variant,"source_sha256":probe_source,
          "arm_source_sha256":before,"probe_sha256":hash_file(probe),"probe_host_sha256":hash_file(host),
          "probe_host_tests_sha256":hash_file(tests_file),"toolchain_sha256":compiler},sort_keys=True),flush=True)
    events=cargo_events(run(target,env,src,"cargo","test","--lib","--no-run",*FLAGS,
                            "-p","proteus-extension","--message-format=json"))
    probe_event=select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",True)
    assert probe_event["fresh"] is False,"instrumented SDK unit executable was cached in this arm"
    proof=artifact_receipt(probe_event,target,tier+"/"+variant+"/probe-exe",SDK,probe_source,compiler)
    check_files(target,proof)
    exe=target/next(iter(proof))
    probe_env=dict(env,R79_ADOPTS="yes" if variant=="candidate" else "no")
    first=split_probe(run(target,probe_env,src/"sdk",exe,"--exact",PROBE,"--nocapture","--test-threads=1"))
    for _ in range(4):
        assert split_probe(run(target,probe_env,src/"sdk",exe,"--exact",PROBE,"--nocapture","--test-threads=1"))==first
    check_files(target,proof)
    assert source_tree(src,omit_git=True)==probe_source
    return wire,first


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_git",type=Path)
    p.add_argument("m150_source",type=Path)
    p.add_argument("prior",type=Path,nargs=5)
    p.add_argument("--target",required=True,type=Path)
    p.add_argument("--lock",required=True,type=Path)
    p.add_argument("--admit-exclusive",action="store_true")
    a=p.parse_args()
    a.stock_git=a.stock_git.resolve(strict=True)
    a.m150_source=a.m150_source.resolve(strict=True)
    a.prior=[item.resolve(strict=True) for item in a.prior]
    target=a.target.resolve(strict=True)
    assert hash_file(HERE/"source.patch")==PATCH_SHA
    assert target.is_dir() and Path(os.environ["CARGO_HOME"]).is_dir()
    assert source_tree(a.m150_source)==M150 and [hash_file(item) for item in a.prior]==OVERLAYS
    print("preflight free source, target bytes",shutil.disk_usage(HERE).free,shutil.disk_usage(target).free,flush=True)
    if not a.admit_exclusive:
        print("Read-only preflight: compiler not started")
        return
    with a.lock.resolve(strict=True).open("rb") as gate:
        fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)>=512*2**20
        env = dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_NET_OFFLINE="true",
                   CARGO_INCREMENTAL="0",CARGO_BUILD_JOBS="1",TZ="UTC",LC_ALL="C")
        chain={}
        for tool, args in [("rustc",["-Vv"]),("rustdoc",["--version"]),("cargo",["--version"]),("rustfmt",["--version"])]:
            binary=Path(shutil.which(tool,path=env["PATH"])).resolve(strict=True)
            chain[tool]={"sha256":hash_file(binary),"version":run(target,env,HERE,binary,*args).decode().strip()}
        assert "release: 1.95.0" in chain["rustc"]["version"]
        print("toolchain",json.dumps(chain,sort_keys=True),flush=True)
        with tempfile.TemporaryDirectory(prefix="badge-envelope-r80-",dir=HERE) as spool:
            for tier in ("base",TIER):
                arms=[arm(Path(spool),tier,variant,a,target,env,chain) for variant in ("stock","candidate")]
                stock,candidate=arms
                assert stock[0]==candidate[0],tier
                for name,value in stock[0].items():
                    print(tier,"ordinary",name,len(value.splitlines()),len(value),sha256(value).hexdigest(),flush=True)
                for name,(_,meters) in zip(("stock","candidate"),arms,strict=True):
                    for row in meters:
                        print(tier,"meter",name,*row,flush=True)
                control_sizes(stock[1],candidate[1])
                print(tier,"differential-pass",flush=True)
        assert source_tree(a.m150_source)==M150 and [hash_file(p) for p in a.prior]==OVERLAYS
        print("verified retained inputs and final free source, target bytes",shutil.disk_usage(HERE).free,
              shutil.disk_usage(target).free,flush=True)


if __name__=="__main__":
    main()
