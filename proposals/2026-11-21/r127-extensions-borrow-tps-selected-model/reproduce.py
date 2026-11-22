#!/usr/bin/env python3
"""Borrow TPS selected model keys; exact release protocol and scoped reset allocation proof."""
import argparse
from base64 import b64decode
import fcntl
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess as sp
import tarfile
import tempfile
import sys
import time


HERE = Path(__file__).resolve().parent
PIN = "892f627570369ed60d7205eb0d351c753ec4305f"
PREIMAGE = {
    "base": ("892f627570369ed60d7205eb0d351c753ec4305f",
             "ca913bb88e38351a26691d2c1c0e0232b8b132645cf7931133470a48e6a3bca4",
             "ed4eaac8c8903977169ed19ab47a4242d4d8b32d1b9ab37054fac80c9d87396b"),
    "composed": ("dc67ed515f7e1a6aa41e3c87132e4243a5507c35",
                 "8a6bb61b25169cad962af8c1167a98cb75e0bf1c2240931a2e257f22ede4910d",
                 "11a7a344cf9eb80e819f310a97d8d0747f0b472d83f78b08f570d3fca2496256"),
}
MAIN_PREIMAGE = "b9af6729274bacaf762377dbbfd6d8242034f9aa249916ca09340ed8544da348"
CONTEXT_OVERLAY = "4bc35258f3d438fb4a9985a37fd97e2f58f073b55c085066ed41ad0a38305a52"
PATCH = '0b9706f4f6b894a71c683e6f427938938ce00a1ad20304e0670ae02a772b36f9'
CANDIDATE = {
    "base": "ef3df0aadcd69e47358ac6546d933b94028f208758cb007a7801f413b9f2a03d",
    "composed": "566e0a0023c7a6ecdd3cd1ebbfa1ad100b1651fd8c2ebe64b97f30370c795de7",
}
BEFORE_446 = "174c79453dacb3ad3cad54cd692b235a3377da428bc7e4058ebb92898fa46b29"
SDK = "sdk/Cargo.toml"
PKG = "packages/tps/Cargo.toml"
MAIN_RS = "packages/tps/src/main.rs"
SAMPLE_RS = "packages/tps/src/sample.rs"
PROBE = "r127_probe::measure_tps_identity"
CASES = ("same-once","same-dozen","unicode-dozen","partial-name","bad-provider","empty-pair",
         "provider-reset","name-reset","session-reset","malformed-reset","missing-session")
FLAGS = ["--release","--locked","--offline","-j1","-p","extension-tps","--bin","tps"]
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


def split_probe(raw):
    found = re.findall(rb"^ops ([a-z-]+)" + rb" (\d+)" * 9 + rb"$", raw, re.M)
    meters = {case.decode():tuple(map(int,nums)) for case,*nums in found}
    trees = re.findall(rb"^shape ([a-z-]+) (.+)$",raw,re.M)
    assert tuple(meters)==tuple(k.decode() for k,_ in trees)==CASES,raw[-3000:]
    assert b"test result: ok. 1 passed; 0 failed; 0 ignored;" in raw
    return meters,trees


def assert_measures(before,after):
    a,b = before[0],after[0]
    assert before[1]==after[1], "sole model invalidation changed stored session/model/flags/deadline/data"
    for name,prev in a.items():
        post = b[name]
        reps,p,n,reads,resets,owned,owned_bytes,calls,requested = prev
        assert post[:5]==prev[:5] and reads==reps, (name,prev,post)
        if name in ("same-once","same-dozen","unicode-dozen"):
            assert p+n>=20 and p>0 and n>0 and owned==2*reps and owned_bytes==(p+n)*reps
            assert resets==0 and post[5:]==(0,0,0,0)
            assert (calls,requested)==(2*reps,(p+n)*reps)
        elif name in ("partial-name","malformed-reset"):
            assert n==0 and post[5:]==(0,0,calls-1,requested-p)
            assert (owned,owned_bytes)==(1,p) and p>0
        elif name=="bad-provider":
            assert prev==post and post[5:]==(0,0,0,0)
        elif name=="empty-pair":
            assert resets==0 and prev[5:]==(2,0,0,0) and post[5:]==(0,0,0,0)
        else:
            assert resets==1 and prev==post and owned==2 and calls>=2 and requested>=p+n


def instrument(src,variant):
    main,sample = (src/MAIN_RS,src/SAMPLE_RS)
    original_main,original_sample = (main.read_text(),sample.read_text())
    start = original_main.index("        let state = host.state.as_ref().unwrap_or")
    stop = original_main.index("        self.running = ",start)
    seam = original_main[start:stop]
    markers = [
        ("let model = Model::selected(state);","r127_probe::read_key();\n        let model = Model::selected(state);"),
        ("*self = Self {","r127_probe::reset();\n            *self = Self {"),
    ]
    if variant=="candidate":
        markers.extend([
            ("provider: provider.to_owned(),","provider: r127_probe::owned(provider),"),
            ("name: name.to_owned(),","name: r127_probe::owned(name),"),
        ])
    for old,new in markers:
        assert seam.count(old)==1,(variant,old)
        seam=seam.replace(old,new)
    end="        if r127_probe::active() { return Ok(()); }\n"
    main.write_text(original_main[:start]+seam+end+original_main[stop:]
                    +"\n#[cfg(test)]\nmod r127_probe {\n"+(HERE/"probe.rs").read_text()+"\n}\n")
    if variant=="stock":
        head=original_sample.index("    pub fn selected(")
        tail=original_sample.index("    pub fn label(",head)
        method=original_sample[head:tail]
        for field in ("provider","name"):
            old=f'model.opt_str("{field}")?.to_owned()'
            assert method.count(old)==1
            method=method.replace(old,f'crate::r127_probe::owned(model.opt_str("{field}")?)')
        sample.write_text(original_sample[:head]+method+original_sample[tail:])
    return original_main,original_sample


def stamp_release_inputs(src, target, source_paths, scope, expected_digest):
    """Invalidate older Cargo inputs without changing canonical bytes or cache."""
    release = target / "release"
    if release.exists():
        assert release.is_dir() and not release.is_symlink()
    latest = 0
    old_regular = 0
    for path in release.rglob("*"):
        meta = path.lstat()
        if stat.S_ISREG(meta.st_mode):
            latest = max(latest, meta.st_mtime_ns)
            old_regular += 1
    original = {rel: ((src/rel).stat().st_mode, hash_file(src/rel)) for rel in source_paths}
    stamp = time.time_ns()
    assert stamp > latest, "warm release artifact mtime is not older than a fresh scratch stamp"
    observed = {}
    for rel in source_paths:
        path = src/rel
        meta = path.lstat()
        assert stat.S_ISREG(meta.st_mode) and path.resolve() == path
        os.utime(path, ns=(meta.st_atime_ns, stamp), follow_symlinks=False)
        item = path.stat()
        assert latest < item.st_mtime_ns <= time.time_ns(), "cannot establish strict target/source age ordering"
        assert (item.st_mode,hash_file(path)) == original[rel]
        observed[rel] = item.st_mtime_ns
    assert source_tree(src)==expected_digest
    print("freshness",json.dumps({"scope":scope,"existing_target_release_regular":old_regular,
          "existing_target_max_mtime_ns":latest,"scratch_source_mtime_ns":observed,
          "source_tree_sha256_unchanged":expected_digest},sort_keys=True),flush=True)


def arm(src, tier, variant, target, env, toolchain):
    before = source_tree(src)
    lock = PREIMAGE[tier][2]
    assert hash_file(src/"Cargo.lock") == lock
    assert before==(PREIMAGE[tier][1] if variant=="stock" else CANDIDATE[tier])
    run(target,env,src,"cargo","fmt","-p","extension-tps","--","--check")
    compiler = sha256(json.dumps(toolchain,sort_keys=True).encode()).hexdigest()
    scope = tier + "/" + variant
    stamp_release_inputs(src,target,("sdk/src/lib.rs",MAIN_RS,SAMPLE_RS),scope+"/unit",before)
    sdk_state = {"files":None}
    print("arm",json.dumps({"tier":tier,"variant":variant,"upstream":PIN,"preimage_commit":PREIMAGE[tier][0],
            "source_sha256":before,"lock_sha256":lock,"toolchain_sha256":compiler,
            "main_rs_sha256":hash_file(src/MAIN_RS),"sample_rs_sha256":hash_file(src/SAMPLE_RS),"profile":"release"},sort_keys=True),flush=True)

    def resolve(events, phase, src_hash, test):
        sdk = select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
        proof = artifact_receipt(sdk,target,scope+"/"+phase+"-sdk",SDK,src_hash,compiler)
        if sdk["fresh"]:
            assert sdk_state["files"] == proof, "SDK reused outside this verified tier export or artifact hash differs"
        else:
            sdk_state["files"] = proof
        check_files(target,proof)
        bin = select_artifact(events,src,PKG,MAIN_RS,"tps","bin",test)
        assert not bin["fresh"], (scope,phase,"release TPS binary not freshly built")
        files = artifact_receipt(bin,target,scope+"/"+phase,PKG,src_hash,compiler)
        check_files(target,files)
        return target/next(iter(files)),files

    test_args = ("cargo","test","--no-run",*FLAGS,"--message-format=json")
    events = cargo_events(run(target,env,src,*test_args))
    path,proof = resolve(events,"unit",before,True)
    raw = run(target,env,(src/PKG).parent,path)
    count = (4 if tier=="base" else 6) + (variant=="candidate")
    assert_suite(raw,count)
    check_files(target,proof)
    check_files(target,sdk_state["files"])
    if variant=="candidate":
        assert b"selected_model_borrows_two_typed_fields ... ok" in raw
    print("unit-pass",tier,variant,count,flush=True)

    events = cargo_events(run(target,env,src,"cargo","build",*FLAGS,"--message-format=json"))
    path,proof = resolve(events,"wire",before,False)
    raw = run(target,env,src,sys.executable,"-E","-B",HERE/"fixtures.py",path,src)
    wire = [(name,b64decode(stdout,validate=True),reads) for name,stdout,reads in map(json.loads,raw.splitlines())]
    assert [name for name,_,_ in wire] == ["idle-updates","controls"]
    check_files(target,proof)
    check_files(target,sdk_state["files"])
    assert source_tree(src) == before

    main_rs,sample_rs = src/MAIN_RS,src/SAMPLE_RS
    originals = instrument(src,variant)
    probe_src = source_tree(src)
    print("probe-source",json.dumps({"tier":tier,"variant":variant,"source_sha256":probe_src,
            "arm_source_sha256":before,"probe_template_sha256":hash_file(HERE/"probe.rs"),
            "probe_main_sha256":hash_file(main_rs),"probe_sample_sha256":hash_file(sample_rs),
            "toolchain_sha256":compiler},sort_keys=True),flush=True)
    try:
        stamp_release_inputs(src,target,(MAIN_RS,SAMPLE_RS),scope+"/probe",probe_src)
        events = cargo_events(run(target,env,src,*test_args))
        path,proof = resolve(events,"probe",probe_src,True)
        def measure():
            result = split_probe(run(target,env,(src/PKG).parent,path,"--exact",PROBE,"--nocapture","--test-threads=1"))
            check_files(target,proof)
            return result
        result = measure()
        assert all(measure()==result for _ in range(4))
        check_files(target,sdk_state["files"])
        assert source_tree(src) == probe_src
    finally:
        for path,original in zip((main_rs,sample_rs),originals,strict=True):
            path.write_text(original)
    assert source_tree(src) == before
    return wire,result


def verify_export(src,tier):
    _,digest,lock = PREIMAGE[tier]
    assert src.is_dir() and not src.is_symlink() and src.resolve() == src
    assert source_tree(src)==digest and hash_file(src/"Cargo.lock")==lock
    assert sum(p.is_file() or p.is_symlink() for p in src.rglob("*"))==467
    assert all(".git" not in p.relative_to(src).parts and "target" not in p.relative_to(src).parts
               for p in src.rglob("*"))
    assert hash_file(src/MAIN_RS)==MAIN_PREIMAGE


def export(repo,tier,src,target,env,overlay):
    commit = PREIMAGE[tier][0]
    payload = run(target,env,repo,"git","archive","--format=tar",commit)
    src.mkdir(mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        archive.extractall(src,filter="data")
    if tier=="composed":
        assert source_tree(src)==BEFORE_446
        run(target,env,src,"git","apply","--check","--whitespace=error",overlay)
        run(target,env,src,"git","apply","--whitespace=error",overlay)
        run(target,env,src,"git","apply","--reverse","--check","--whitespace=error",overlay)
    verify_export(src,tier)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_git",type=Path)
    p.add_argument("composed_git",type=Path)
    p.add_argument("--target",required=True,type=Path)
    p.add_argument("--lock",required=True,type=Path)
    p.add_argument("--admit-exclusive",action="store_true")
    p.add_argument("--context-446",type=Path,required=True,help="exact #446 previously verified Overlay")
    a=p.parse_args()
    repos={tier:repo.resolve(strict=True) for tier,repo in (("base",a.stock_git),("composed",a.composed_git))}
    target=a.target.resolve(strict=True)
    home=Path(os.environ["CARGO_HOME"]).resolve(strict=True)
    patch=HERE/"source.patch"
    overlay=a.context_446.resolve(strict=True)
    assert hash_file(overlay)==CONTEXT_OVERLAY and hash_file(patch)==PATCH and not os.environ.get("PYTHONOPTIMIZE")
    assert target.is_dir() and home.is_dir() and target.stat().st_dev==home.stat().st_dev!=HERE.stat().st_dev
    env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_NET_OFFLINE="true",CARGO_INCREMENTAL="0",
             CARGO_BUILD_JOBS="1",TZ="UTC",LC_ALL="C",PYTHONDONTWRITEBYTECODE="1",
             CARGO_ENCODED_RUSTFLAGS="",GIT_OPTIONAL_LOCKS="0")
    env.pop("RUSTFLAGS",None)
    for key in ("RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","RUSTC","RUSTDOC"):
        assert not env.get(key), ("unexpected tool override",key)
    for tier,repo in repos.items():
        assert run(target,env,repo,"git","cat-file","-t",PREIMAGE[tier][0]).strip()==b"commit"
        assert sha256(run(target,env,repo,"git","show",f"{PREIMAGE[tier][0]}:{MAIN_RS}")).hexdigest()==MAIN_PREIMAGE
    assert run(target,env,repos["composed"],"git","rev-parse","HEAD").decode().strip()==PREIMAGE["composed"][0]
    assert not run(target,env,repos["composed"],"git","status","--porcelain")
    assert source_tree(repos["composed"],omit_git=True)==BEFORE_446
    print("preflight free source, target bytes",shutil.disk_usage(HERE).free,shutil.disk_usage(target).free,flush=True)
    if not a.admit_exclusive:
        print("Read-only preflight: no export, formatter, compiler, test or wire started")
        return
    with a.lock.resolve(strict=True).open("rb") as shared:
        fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert shutil.disk_usage(HERE).free >= (512+32)*2**20 and shutil.disk_usage(target).free >= (512+48)*2**20
        assert min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free) >= 512*2**20
        chain={}
        for tool,args in [("rustc",["-Vv"]),("cargo",["--version"]),("rustfmt",["--version"])]:
            executable=Path(shutil.which(tool,path=env["PATH"])).resolve(strict=True)
            chain[tool]={"sha256":hash_file(executable),"version":run(target,env,HERE,executable,*args).decode().strip()}
        assert "release: 1.95.0" in chain["rustc"]["version"]
        print("toolchain",json.dumps(chain,sort_keys=True),flush=True)
        spool = Path(tempfile.mkdtemp(prefix="tps-model-r127-",dir=HERE.parent))
        for tier,repo in repos.items():
            src=spool/tier
            export(repo,tier,src,target,env,overlay)
            run(target,env,src,"git","apply","--check","--whitespace=error",patch)
            left=arm(src,tier,"stock",target,env,chain)
            run(target,env,src,"git","apply","--whitespace=error",patch)
            run(target,env,src,"git","apply","--reverse","--check","--whitespace=error",patch)
            right=arm(src,tier,"candidate",target,env,chain)
            assert left[0]==right[0],tier
            assert_measures(left[1],right[1])
            for case,stdout,reads in left[0]:
                print(tier,"wire",case,len(stdout.splitlines()),len(stdout),sha256(stdout).hexdigest(),
                      json.dumps(reads,ensure_ascii=False,separators=(",",":")),"writes 0 stderr 0",flush=True)
            for variant,(_,sample) in zip(("stock","candidate"),(left,right),strict=True):
                counters,shapes=sample
                for case,nums in counters.items():
                    print(tier,"ops",variant,case,*nums,flush=True)
                print(tier,"projection-shapes",variant,len(shapes),sha256(b"\n".join(b" ".join(m) for m in shapes)).hexdigest(),flush=True)
            print(tier,"differential-pass",flush=True)
        assert sorted(p.name for p in spool.iterdir())==["base","composed"]
        assert source_tree(repos["composed"],omit_git=True)==BEFORE_446 and hash_file(overlay)==CONTEXT_OVERLAY
        assert not run(target,env,repos["composed"],"git","status","--porcelain")
        print("verified retained inputs and final free source, target bytes",shutil.disk_usage(HERE).free,
              shutil.disk_usage(target).free,flush=True)


if __name__ == "__main__":
    main()
