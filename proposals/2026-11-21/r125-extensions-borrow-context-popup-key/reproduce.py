#!/usr/bin/env python3
"""Warm Context key borrowing; exact GET-only wire and scoped key work."""
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
                 "174c79453dacb3ad3cad54cd692b235a3377da428bc7e4058ebb92898fa46b29",
                 "11a7a344cf9eb80e819f310a97d8d0747f0b472d83f78b08f570d3fca2496256"),
}
MAIN_PREIMAGE = "4412f27c9d33a3754c5b8d0499e9e0051cc226bde825a597ac35025f61164441"
PATCH = "4bc35258f3d438fb4a9985a37fd97e2f58f073b55c085066ed41ad0a38305a52"
SDK = "sdk/Cargo.toml"
PKG = "packages/context/Cargo.toml"
MAIN_RS = "packages/context/src/main.rs"
PROBE = "r125_probe::measure_actual_popup_decision"
CASES = ("short-one", "short-dozen", "long-one", "long-dozen", "cold", "stale",
         "new-view", "no-session", "absent-state", "field-missing")
FLAGS = ["--release", "--locked", "--offline", "-j1", "-p", "extension-context"]
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
    found = re.findall(rb"^ops ([a-z-]+)" + rb" (\d+)" * 15 + rb"$", raw, re.M)
    meters = {case.decode(): tuple(map(int, nums)) for case, *nums in found}
    trees = re.findall(rb"^shape ([a-z-]+) (.+)$", raw, re.M)
    assert tuple(meters) == tuple(k.decode() for k, _ in trees) == CASES, raw[-3000:]
    assert b"test result: ok. 1 passed; 0 failed; 0 ignored;" in raw
    return meters, trees


def assert_measures(before, after):
    a, b = before[0], after[0]
    assert before[1] == after[1], "cache hit/refresh and original key bytes changed"
    for name, prev in a.items():
        post = b[name]
        reps, n, key_bytes, clones, c_bytes, enc, builds, b_bytes, hit, miss, absent, new, old, alloc, size = prev
        assert post[:3] == prev[:3] and post[8:13] == prev[8:13], (name,prev,post)
        selected = reps - absent
        assert (clones,c_bytes,builds,b_bytes) == (selected,selected*n,selected,selected*key_bytes)
        assert (post[3],post[4],post[5],post[6],post[7]) == (0,0,enc,miss,miss*key_bytes)
        assert enc == (0 if name in ("no-session","absent-state") else reps)
        assert hit + miss + absent == reps
        assert (post[13] <= alloc and post[14] <= size), (name,prev,post)
        if name in ("short-one","short-dozen","long-one","long-dozen"):
            assert hit == reps and reps in (1,12) and n>=16
            assert alloc - post[13] >= 2*reps and size - post[14] >= reps*(n+key_bytes), (name,prev,post)
        elif name == "no-session":
            assert prev == post and alloc == size == 0
        elif miss:
            assert alloc - post[13] == 1 and size - post[14] == n, (name,prev,post)


def instrument(path, variant):
    original = path.read_text()
    start = original.index("    fn popup(")
    end = original.index("\n    }\n}", start)
    fn = original[start:end]
    changes = {
        'return Ok(muted("Сессия не открыта."));': (
            'if r125_probe::no_session() { return Ok(Value::Null); }\n'
            '            return Ok(muted("Сессия не открыта."));'),
        '.map(|state| state.at("context").to_string())': (
            '.map(|state| { r125_probe::serialized(); state.at("context").to_string() })'),
        'let key = format!("{session}\\n{usage}");': (
            'let key = r125_probe::key_built(format!("{session}\\n{usage}"));'),
        'host.is_shown(view)': 'r125_probe::shown(host, view)',
        'self.snapshot = Some((key, host.api("/context", &[])?));': (
            'if r125_probe::active() { r125_probe::cache_miss(key); return Ok(Value::Null); }\n'
            '            self.snapshot = Some((key, host.api("/context", &[])?));'),
        'let snapshot = &self.snapshot': (
            'if r125_probe::cache_hit() { return Ok(Value::Null); }\n'
            '        let snapshot = &self.snapshot'),
    }
    if variant == "stock":
        changes["host.session.clone()"] = "r125_probe::cloned_session(host.session.clone())"
    for old,new in changes.items():
        assert fn.count(old)==1,(variant,old)
        fn=fn.replace(old,new)
    adapter = ('fn matches_compact_key(known: &str, session: &str, usage: &str) -> bool { ' +
               ('known == format!("{session}\\n{usage}")' if variant == "stock" else 'key_matches(known, session, usage)') +
               ' }')
    path.write_text(original[:start]+fn+original[end:]+"\n#[cfg(test)]\nmod r125_probe {\n"+
                    (HERE/"probe.rs").read_text()+"\n"+adapter+"\n}\n")
    return original


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
    run(target,env,src,"cargo","fmt","-p","extension-context","--","--check")
    compiler = sha256(json.dumps(toolchain,sort_keys=True).encode()).hexdigest()
    scope = tier + "/" + variant
    stamp_release_inputs(src,target,("sdk/src/lib.rs",MAIN_RS),scope+"/unit",before)
    sdk_state = {"files":None}
    print("arm",json.dumps({"tier":tier,"variant":variant,"upstream":PIN,"preimage_commit":PREIMAGE[tier][0],
            "source_sha256":before,"lock_sha256":lock,"toolchain_sha256":compiler,
            "main_rs_sha256":hash_file(src/MAIN_RS),"profile":"release"},sort_keys=True),flush=True)

    def resolve(events, phase, src_hash, test):
        sdk = select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
        proof = artifact_receipt(sdk,target,scope+"/"+phase+"-sdk",SDK,src_hash,compiler)
        if sdk["fresh"]:
            assert sdk_state["files"] == proof, "SDK reused outside this verified tier export or artifact hash differs"
        else:
            sdk_state["files"] = proof
        check_files(target,proof)
        bin = select_artifact(events,src,PKG,MAIN_RS,"context","bin",test)
        assert not bin["fresh"], (scope,phase,"release Context binary not freshly built")
        files = artifact_receipt(bin,target,scope+"/"+phase,PKG,src_hash,compiler)
        check_files(target,files)
        return target/next(iter(files)),files

    test_args = ("cargo","test","--no-run",*FLAGS,"--message-format=json")
    events = cargo_events(run(target,env,src,*test_args))
    path,proof = resolve(events,"unit",before,True)
    raw = run(target,env,(src/PKG).parent,path)
    count = (3 if tier=="base" else 4) + (variant=="candidate")
    assert_suite(raw,count)
    check_files(target,proof)
    check_files(target,sdk_state["files"])
    if variant=="candidate":
        assert b"borrowed_key_requires_exact_delimiter_and_usage ... ok" in raw
    print("unit-pass",tier,variant,count,flush=True)

    events = cargo_events(run(target,env,src,"cargo","build",*FLAGS,"--bin","context","--message-format=json"))
    path,proof = resolve(events,"wire",before,False)
    raw = run(target,env,src,sys.executable,"-E","-B",HERE/"fixtures.py",path,src)
    wire = [(name,b64decode(stdout,validate=True),reads) for name,stdout,reads in map(json.loads,raw.splitlines())]
    assert [name for name,_,_ in wire] == ["popup","state-shapes","controls"]
    check_files(target,proof)
    check_files(target,sdk_state["files"])
    assert source_tree(src) == before

    main_rs = src/MAIN_RS
    original = instrument(main_rs,variant)
    probe_src = source_tree(src)
    print("probe-source",json.dumps({"tier":tier,"variant":variant,"source_sha256":probe_src,
            "arm_source_sha256":before,"probe_template_sha256":hash_file(HERE/"probe.rs"),
            "probe_main_sha256":hash_file(main_rs),"toolchain_sha256":compiler},sort_keys=True),flush=True)
    try:
        stamp_release_inputs(src,target,(MAIN_RS,),scope+"/probe",probe_src)
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
        main_rs.write_text(original)
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


def export(repo,tier,src,target,env):
    commit = PREIMAGE[tier][0]
    payload = run(target,env,repo,"git","archive","--format=tar",commit)
    src.mkdir(mode=0o700)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        archive.extractall(src,filter="data")
    verify_export(src,tier)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_git",type=Path)
    p.add_argument("composed_git",type=Path)
    p.add_argument("--target",required=True,type=Path)
    p.add_argument("--lock",required=True,type=Path)
    p.add_argument("--admit-exclusive",action="store_true")
    p.add_argument("--reuse-stock-export",type=Path,
                   help="reuse only an exact unmodified stock-only spool from a pre-execution HOLD")
    a=p.parse_args()
    repos={tier:repo.resolve(strict=True) for tier,repo in (("base",a.stock_git),("composed",a.composed_git))}
    target=a.target.resolve(strict=True)
    home=Path(os.environ["CARGO_HOME"]).resolve(strict=True)
    patch=HERE/"source.patch"
    assert hash_file(patch)==PATCH and not os.environ.get("PYTHONOPTIMIZE")
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
    assert source_tree(repos["composed"],omit_git=True)==PREIMAGE["composed"][1]
    reuse = None
    if a.reuse_stock_export is not None:
        reuse = a.reuse_stock_export.absolute()
        assert reuse.resolve(strict=True)==reuse and reuse.parent==HERE.parent and reuse.is_dir()
        assert re.fullmatch(r"context-key-r125-[a-z0-9_]+",reuse.name)
        assert [entry.name for entry in reuse.iterdir()]==["base"]
        verify_export(reuse/"base","base")
        print("reverified sole previous stock-only export",reuse.name,flush=True)
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
        spool = reuse if reuse is not None else Path(tempfile.mkdtemp(prefix="context-key-r125-",dir=HERE.parent))
        for tier,repo in repos.items():
            src=spool/tier
            if reuse is not None and tier=="base":
                assert [entry.name for entry in spool.iterdir()]==["base"]
                verify_export(src,tier)
            else:
                export(repo,tier,src,target,env)
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
        assert source_tree(repos["composed"],omit_git=True)==PREIMAGE["composed"][1]
        assert not run(target,env,repos["composed"],"git","status","--porcelain")
        print("verified retained inputs and final free source, target bytes",shutil.disk_usage(HERE).free,
              shutil.disk_usage(target).free,flush=True)


if __name__ == "__main__":
    main()
