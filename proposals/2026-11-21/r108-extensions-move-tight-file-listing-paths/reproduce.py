#!/usr/bin/env python3
"""Files tight decoded listing paths and exact GET-only wire with fresh Cargo artifacts."""
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
    "d001261ce6023e500ac2643a5ff122793bebea2eb556b29d170d6c48d9813439",
    "fa738489ad56bd5793a7722b5e3836866f7657e7b595e6c16a9833ba443e66ee",
    "b2e845c6844dd7f10476449d68db7611a51744395d37c5297792e1d356f5d0d7",
    "a39f22638871cfb43db33d76eb51b98c3ee221a7f24e50f677870da53a3348e4",
    "cb776c425172381af8e2ff38df6bf995d4a751aae95795554c4e4953c49bd0d7",
    "39d87fea375d8d355310869f23b01b5ff82a20672ae001a507d8e3fd0acc5128",
    "2701f3e3b9ab9c55c22100c9cf60d3d4c93ef26a4ebfbf8f95e60b57f4ade56d",
    "c43681c15629e03f3faba7276d731230802fba7c2d2b7c17b592434eff0cad83",
    "5c3a2c515fd916bc833daf04fc4be423ad8d51c49458d3103e1917b07323b47f",
    "d7bf538400f18f99950e54965179fa00aa6658ffd238378038ccc32da2b458e6",
    "22be1fd2c18699ff4122b057d9bdd00a89907d193d1dfdc1468b6cf2a304974a",
    "749812ef18301c487d987bfc878ff1844159df941f1d94346025600fc7af132a",
    "7b281e1430ef8cce4c49d8dcafb271d77d950bf6d2128a2d6d414692e280a75f",
]

START_COMPOSED = "f577f32ab08f57859a72eafc50114fb3559c78c2f7cea6d64c90f7e40125b4be"
LOCKS = {
    "base": "ed4eaac8c8903977169ed19ab47a4242d4d8b32d1b9ab37054fac80c9d87396b",
    "composed": "11a7a344cf9eb80e819f310a97d8d0747f0b472d83f78b08f570d3fca2496256",
}
PATCH = {'base': ('source.patch', '5a014ad618c4c63de962e4c3cdf10507ec665e935093056804cb8745f7aabbd8'), 'composed': ('cumulative.patch', 'a6c001b9d1d53b8a5d1a83a22d7eecabbbeee92913e06af4246c9adef11f9f1b')}
SDK = "sdk/Cargo.toml"
PKG = "packages/files/Cargo.toml"
PKG_TESTS = "packages/files/src/tree_tests.rs"
MAIN_RS = "packages/files/src/main.rs"
TREE_RS = "packages/files/src/tree.rs"
OPS_RS = "packages/files/src/operations.rs"
PROBE = "tree::r108_probe::measure_listing_path_move"
CASES = ("absent","empty","one","ordinary-small","ordinary","mixed")
FLAGS = ["--release", "--locked", "--offline", "-j1", "-p", "extension-files"]
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
    found = re.findall(rb"^ops ([a-z-]+)" + rb" (\d+)" * 11 + rb"$",raw,re.M)
    meters = {case.decode():tuple(map(int,nums)) for case,*nums in found}
    trees = re.findall(rb"^tree ([a-z-]+) (\{[^\n]*\})$",raw,re.M)
    assert tuple(meters)==tuple(k.decode() for k,_ in trees)==CASES,raw[:2000]
    assert b"test result: ok. 1 passed; 0 failed; 0 ignored;" in raw,raw[-2000:]
    return meters,trees


def control_sizes(before,after):
    assert before[1]==after[1]
    for case,left in before[0].items():
        right=after[0][case]
        n,kept,payload,cap,slot,vcap,eligible,eligible_bytes,moved,calls,requested=left
        assert cap==payload and moved==0 and kept<=n and vcap>=kept,(case,left)
        assert right==(n,kept,payload,cap,slot,vcap,eligible,eligible_bytes,eligible,
                      calls-eligible,requested-eligible_bytes),(case,left,right)
        if case in ("one","ordinary-small","ordinary"):
            assert eligible==n==kept and eligible_bytes==payload and 32<=payload/n<=64,(case,left,right)
        if case=="mixed":
            assert 0<eligible<kept<n and eligible_bytes<payload,(case,left,right)


def instrument(src,tier,variant):
    tree=src/TREE_RS
    text=tree.read_text()
    probe=tree.parent/"tree"/"r108_probe.rs"
    probe.parent.mkdir(exist_ok=True)
    assert not probe.exists()
    borrow="&" if variant=="stock" else ""
    name='entry.name.as_str()' if tier=="base" else 'entry.name()'
    adapter=f"""
fn admit(value:Value) -> Listing {{ Listing::parse({borrow}value) }}
fn entry_name(entry:&Entry) -> &str {{ {name} }}
"""
    probe.write_bytes((HERE/"probe.rs").read_bytes()+adapter.encode())
    tree.write_text(text+'\n#[cfg(test)]\nmod r108_probe;\n')
    return probe,tree


def arm(root, tier, variant, args, target, env, toolchain):
    src = root / (tier + "-" + variant)
    patch = HERE / PATCH[tier][0]
    overlays = []
    if tier == "base":
        sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",args.stock_git,src],check=True)
        run(target,env,src,"git","checkout","-q","--detach",PIN)
        assert run(target,env,src,"git","rev-parse","HEAD").decode().strip() == PIN
        assert not run(target,env,src,"git","status","--porcelain")
    else:
        shutil.copytree(args.m150_source,src,symlinks=True,copy_function=shutil.copy)
        assert source_tree(src) == M150
        for prior in args.prior:
            run(target,env,src,"git","apply","--check","--whitespace=error",prior)
            run(target,env,src,"git","apply","--whitespace=error",prior)
            overlays.append(hash_file(prior))
        assert source_tree(src) == START_COMPOSED
    assert hash_file(src / "Cargo.lock") == LOCKS[tier]
    run(target,env,src,"git","apply","--check","--whitespace=error",patch)
    if variant == "candidate":
        run(target,env,src,"git","apply","--whitespace=error",patch)
        run(target,env,src,"git","apply","--reverse","--check",patch)
        overlays.append(hash_file(patch))
    run(target,env,src,"cargo","fmt","-p","extension-files","--","--check")
    before = source_tree(src,omit_git=True)
    compiler = sha256(json.dumps(toolchain,sort_keys=True).encode()).hexdigest()
    scope = tier + "/" + variant
    print("arm",json.dumps({"tier":tier,"variant":variant,"upstream":PIN,"source_sha256":before,
          "overlays":overlays,"lock_sha256":LOCKS[tier],"toolchain_sha256":compiler,
          "main_rs_sha256":hash_file(src/MAIN_RS),"tree_rs_sha256":hash_file(src/TREE_RS),"operations_rs_sha256":hash_file(src/OPS_RS),"tests_sha256":hash_file(src/PKG_TESTS),
          "profile":"release"},sort_keys=True),flush=True)
    count = (37 if tier == "base" else 42) + (variant == "candidate")
    sdk_files = None

    def resolve(events, phase, source_hash, test):
        nonlocal sdk_files
        sdk = select_artifact(events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
        sdk_proof = artifact_receipt(sdk,target,scope+"/"+phase+"-sdk",SDK,source_hash,compiler)
        if sdk["fresh"]:
            assert sdk_files == sdk_proof, "cached SDK is not proven same-arm artifact"
        else:
            sdk_files = sdk_proof
        check_files(target,sdk_files)
        binary = select_artifact(events,src,PKG,MAIN_RS,"files","bin",test)
        assert binary["fresh"] is False, (scope,phase,"Files must build freshly")
        files = artifact_receipt(binary,target,scope+"/"+phase,PKG,source_hash,compiler)
        check_files(target,files)
        return target/next(iter(files)),files

    events = cargo_events(run(target,env,src,"cargo","test","--no-run",*FLAGS,"--message-format=json"))
    path,proof = resolve(events,"unit",before,True)
    raw = run(target,env,(src/PKG).parent,path)
    assert_suite(raw,count)
    check_files(target,proof)
    check_files(target,sdk_files)
    print("unit-pass",tier,variant,count,flush=True)
    if tier=="composed":
        assert b"listing_names_share_an_exact_path_suffix_and_keep_original_labels ... ok" in raw
        assert b"changed_membership_survives_unknown_status_and_folder_rollup_sees_all_rows ... ok" in raw
    if variant=="candidate":
        assert b"listing_moves_only_tight_raw_paths_and_preserves_defaults ... ok" in raw

    events = cargo_events(run(target,env,src,"cargo","build",*FLAGS,"--bins","--message-format=json"))
    path,proof = resolve(events,"wire",before,False)
    wire = fixtures.replay(path,src,env)
    check_files(target,proof)
    check_files(target,sdk_files)
    assert source_tree(src,omit_git=True) == before

    probe,tree = instrument(src,tier,variant)
    probe_source = source_tree(src,omit_git=True)
    print("probe-source",json.dumps({"tier":tier,"variant":variant,"source_sha256":probe_source,
          "arm_source_sha256":before,"probe_sha256":hash_file(probe),
          "probe_template_sha256":hash_file(HERE/"probe.rs"),"probe_tree_sha256":hash_file(tree),
          "toolchain_sha256":compiler},sort_keys=True),flush=True)
    events = cargo_events(run(target,env,src,"cargo","test","--no-run",*FLAGS,"--message-format=json"))
    path,proof = resolve(events,"probe",probe_source,True)
    def measure():
        result = split_probe(run(target,env,(src/PKG).parent,path,"--exact",PROBE,"--nocapture","--test-threads=1"))
        check_files(target,proof)
        return result
    first = measure()
    assert all(measure() == first for _ in range(4))
    check_files(target,sdk_files)
    assert source_tree(src,omit_git=True) == probe_source
    return wire,first


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_git",type=Path)
    p.add_argument("m150_source",type=Path)
    p.add_argument("prior",type=Path,nargs=18)
    p.add_argument("--target",required=True,type=Path)
    p.add_argument("--lock",required=True,type=Path)
    p.add_argument("--admit-exclusive",action="store_true")
    a = p.parse_args()
    a.stock_git = a.stock_git.resolve(strict=True)
    a.m150_source = a.m150_source.resolve(strict=True)
    a.prior = [item.resolve(strict=True) for item in a.prior]
    target = a.target.resolve(strict=True)
    assert all(hash_file(HERE/name)==digest for name,digest in PATCH.values())
    assert target.is_dir() and Path(os.environ["CARGO_HOME"]).is_dir()
    assert source_tree(a.m150_source) == M150 and [hash_file(item) for item in a.prior] == OVERLAYS
    assert run(target,os.environ,a.stock_git,"git","cat-file","-t",PIN).strip() == b"commit"
    print("preflight free source, target bytes",shutil.disk_usage(HERE).free,shutil.disk_usage(target).free,flush=True)
    if not a.admit_exclusive:
        print("Read-only preflight: compiler not started")
        return
    with a.lock.resolve(strict=True).open("rb") as gate:
        fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free) >= 512*2**20
        env = dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_NET_OFFLINE="true",CARGO_INCREMENTAL="0",
                   CARGO_BUILD_JOBS="1",TZ="UTC",LC_ALL="C",PYTHONDONTWRITEBYTECODE="1",
                   CARGO_ENCODED_RUSTFLAGS="")
        env.pop("RUSTFLAGS",None)
        for custom in ("RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","RUSTC","RUSTDOC"):
            assert not env.get(custom),("unexpected tool override",custom)
        chain = {}
        for tool,args in [("rustc",["-Vv"]),("cargo",["--version"]),("rustfmt",["--version"])]:
            binary = Path(shutil.which(tool,path=env["PATH"])).resolve(strict=True)
            chain[tool] = {"sha256":hash_file(binary),"version":run(target,env,HERE,binary,*args).decode().strip()}
        assert "release: 1.95.0" in chain["rustc"]["version"]
        print("toolchain",json.dumps(chain,sort_keys=True),flush=True)
        with tempfile.TemporaryDirectory(prefix="files-list-path-r108-",dir=HERE) as spool:
            previous_wire = None
            for tier in ("base","composed"):
                stock,candidate = (arm(Path(spool),tier,variant,a,target,env,chain)
                                   for variant in ("stock","candidate"))
                assert stock[0] == candidate[0],tier
                if previous_wire is not None:
                    assert previous_wire == stock[0]
                previous_wire = stock[0]
                payloads,request_lists = stock[0]
                for name,raw,reads in zip(("ordinary","scoped","paths"),payloads,request_lists,strict=True):
                    print(tier,"wire",name,len(raw.splitlines()),len(raw),sha256(raw).hexdigest(),
                          json.dumps(reads,ensure_ascii=False,separators=(",",":")),flush=True)
                for label,(_,meters) in zip(("stock","candidate"),(stock,candidate),strict=True):
                    counters,trees=meters
                    for case,row in counters.items():
                        print(tier,"ops",label,case,*row,flush=True)
                    print(tier,"projection-trees",label,len(trees),sha256(b"\n".join(b" ".join(row) for row in trees)).hexdigest(),flush=True)
                control_sizes(stock[1],candidate[1])
                shapes=tuple(({k:row[:4]+row[5:9] for k,row in sample[0].items()},sample[1])
                              for sample in (stock[1],candidate[1]))
                # #409 retains a different Entry slot and name ownership; only
                # compare logical capacity/path outcomes across these two types.
                if tier=="base":
                    original_shapes=shapes
                else:
                    assert original_shapes==shapes
                print(tier,"differential-pass",flush=True)
        assert source_tree(a.m150_source) == M150 and [hash_file(p) for p in a.prior] == OVERLAYS
        print("verified retained inputs and final free source, target bytes",shutil.disk_usage(HERE).free,
              shutil.disk_usage(target).free,flush=True)


if __name__ == "__main__":
    main()
