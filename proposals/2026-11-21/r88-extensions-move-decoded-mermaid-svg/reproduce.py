#!/usr/bin/env python3
"""Mermaid decoded SVG projections, exact package wire, and fresh Cargo inputs."""
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
import sys
import textwrap

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
]

START_COMPOSED = "72a172bc775db7fdf72a448c9d20b41128a3b0f56d16b63a7c0502da0ba283d7"
LOCKS = {
    "base": "ed4eaac8c8903977169ed19ab47a4242d4d8b32d1b9ab37054fac80c9d87396b",
    "composed": "11a7a344cf9eb80e819f310a97d8d0747f0b472d83f78b08f570d3fca2496256",
}

PATCH_SHA = "a39f22638871cfb43db33d76eb51b98c3ee221a7f24e50f677870da53a3348e4"
SDK = "sdk/Cargo.toml"
PKG = "packages/mermaid-render"
MANIFEST = PKG + "/Cargo.toml"
MAIN_RS = PKG + "/src/main.rs"
WORKER_RS = PKG + "/src/worker.rs"
WIRE_RS = PKG + "/tests/wire.rs"
PROBE = "worker::r88_probe::meter_decoded_svg_projection"
CASES = ("small-escaped","actual-large","synthetic-at-limit","synthetic-over","invalid-dimensions","bad-status")
FLAGS = ["--release","--locked","--offline","-j1","-p","extension-mermaid-render"]
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


def run(target, env, cwd, *cmd, return_status=False):
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
    if status!=0 and not return_status:
        raise RuntimeError((cmd,status,actual.decode(errors="replace"),error.decode(errors="replace")))
    if min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)<256*2**20:
        raise RuntimeError("disk stop floor")
    return (status,actual,error) if return_status else actual


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
    rows=[]
    for tag,*rest in re.findall(rb"^projection ([a-z0-9-]+)" + rb" (\d+)"*7 + rb"$",raw,re.M):
        rows.append((tag.decode(),*map(int,rest)))
    assert tuple(r[0] for r in rows) == CASES,raw
    assert b"test result: ok. 1 passed; 0 failed;" in raw,raw
    return rows


def validate_probe(stock,candidate):
    for left,right in zip(stock,candidate,strict=True):
        name,raw_len,len_,cap,outcap,moved,calls,bytes_=left
        assert left[:5] == right[:5],(left,right)
        assert moved == 0,(left,right)
        if name in CASES[:3]:
            assert 0<len_==cap==outcap,(left,right)
            assert right[5] == 1 and calls-right[6] == 2 and bytes_-right[7] == 2*len_,(left,right)
            if name == "actual-large":
                assert len_>=32*1024,(left,right)
        else:
            assert left==right,(left,right)


def scoped_procfs_probe():
    with sp.Popen([sys.executable,"-c","import sys; sys.stdin.buffer.read()"],stdin=sp.PIPE) as child:
        endpoint=Path("/proc")/str(os.getpid())/"task"/str(os.getpid())/"children"
        try:
            assert str(child.pid) in endpoint.read_text().split()
            return False
        except FileNotFoundError:
            assert child.poll() is None and endpoint.parent.is_dir()
            return True
        finally:
            child.stdin.close()
            assert child.wait(timeout=5)==0


def canonical_wire(target, env, src, exe, procfs_missing):
    rc,raw,err=run(target,env,src,exe,"--test-threads=1",return_status=True)
    if rc == 0:
        assert_suite(raw,2)
        return "2 passed"
    assert rc == 101 and procfs_missing,(rc,raw[-4000:],err)
    assert re.findall(rb"^test [^\n]+ \.\.\. FAILED$",raw,re.M)==[
        b"test different_sessions_share_one_worker_and_last_close_and_eof_reap_it ... FAILED"],raw
    for fragment in [b"test unsupported_mermaid_is_an_addressed_content_error ... ok",
                     b"packages/mermaid-render/tests/wire.rs:155:5",
                     b"left: 0",b"right: 1",
                     b"test result: FAILED. 1 passed; 1 failed; 0 ignored;"]:
        assert fragment in raw,(fragment,raw)
    return "1 passed; 1 failed on existing task-children assertion (independent live-child ENOENT; not a green suite)"


def stock_adapter(text):
    # Lift exactly the stock projection into a private function only in the
    # instrumented stock copy. No source/guard or production-wire change.
    start=text.index('        ensure!(\n            result["ok"]')
    end=text.index('\n    }\n}',start)
    segment=text[start:end]
    assert segment.endswith("Ok(ui::svg(svg, width, height))")
    return (text[:start]+"        svg_root(result)"+text[end:end+8]+"\n\nfn svg_root(result: Value) -> Result<Value> {\n"
            +textwrap.indent(textwrap.dedent(segment),"    ")+"\n}"+text[end+8:])


def arm(spool, tier, variant, args, target, env, chain, node, procfs_missing):
    src=spool/(tier+"-"+variant)
    patch=HERE/"source.patch"
    overlays=[]
    if tier=="base":
        sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",args.stock_git,src],check=True)
        run(target,env,src,"git","checkout","-q","--detach",PIN)
        assert run(target,env,src,"git","rev-parse","HEAD").decode().strip()==PIN
        assert not run(target,env,src,"git","status","--porcelain")
    else:
        shutil.copytree(args.m150_source,src,symlinks=True,copy_function=shutil.copy)
        assert source_tree(src)==M150
        for prior in args.prior:
            run(target,env,src,"git","apply","--check","--whitespace=error",prior)
            run(target,env,src,"git","apply","--whitespace=error",prior)
            overlays.append(hash_file(prior))
        assert source_tree(src)==START_COMPOSED
    assert hash_file(src/"Cargo.lock")==LOCKS[tier]
    run(target,env,src,"git","apply","--check","--whitespace=error",patch)
    if variant=="candidate":
        run(target,env,src,"git","apply","--whitespace=error",patch)
        run(target,env,src,"git","apply","--reverse","--check",patch)
        overlays.append(hash_file(patch))
    run(target,env,src,"cargo","fmt","-p","extension-mermaid-render","--","--check")
    fixtures.check_worker(src/PKG)
    before=source_tree(src,omit_git=True)
    compiler=sha256(json.dumps(chain,sort_keys=True).encode()).hexdigest()
    scope=tier+"/"+variant
    print("arm",json.dumps({"tier":tier,"variant":variant,"upstream":PIN,"source_sha256":before,
          "overlays":overlays,"lock_sha256":LOCKS[tier],"toolchain_sha256":compiler,
          "worker_rs_sha256":hash_file(src/WORKER_RS),"worker_files":fixtures.WORKER_FILES},
          sort_keys=True),flush=True)
    events=cargo_events(run(target,env,src,"cargo","test","--no-run",*FLAGS,"--message-format=json"))
    sdk_files=None
    def sdk_artifact(all_events, phase, source_hash):
        nonlocal sdk_files
        sdk=select_artifact(all_events,src,SDK,"sdk/src/lib.rs","proteus_extension","lib",False,False)
        evidence=artifact_receipt(sdk,target,scope+"/"+phase+"-sdk",SDK,source_hash,compiler)
        if sdk["fresh"]:
            assert evidence==sdk_files,"unproven SDK reuse"
        else:
            sdk_files=evidence
        check_files(target,evidence)
    def binary(all_events, phase, source_hash, source, kind, name, test):
        event=select_artifact(all_events,src,MANIFEST,source,name,kind,test)
        assert event["fresh"] is False,(scope,phase,"target not freshly compiled")
        evidence=artifact_receipt(event,target,scope+"/"+phase,MANIFEST,source_hash,compiler)
        check_files(target,evidence)
        return target/next(iter(evidence)),evidence
    sdk_artifact(events,"ordinary",before)
    unit, unit_receipt=binary(events,"unit",before,MAIN_RS,"bin","mermaid-render",True)
    wiretest, test_receipt=binary(events,"wiretest",before,WIRE_RS,"test","wire",True)
    exe, exe_receipt=binary(events,"real-exe",before,MAIN_RS,"bin","mermaid-render",False)

    count=(9 if tier=="base" else 10)+(2 if variant=="candidate" else 0)
    unit_output=run(target,env,src/PKG,unit,"--test-threads=1")
    assert_suite(unit_output,count)
    check_files(target,unit_receipt)
    print("unit-pass",tier,variant,count,flush=True)
    if variant=="candidate":
        for name in ("validated_svg_root_keeps_exact_wire_and_adopts_the_decoded_string",
                     "svg_root_preserves_validation_order_and_exact_svg_limit"):
            assert f"test worker::tests::{name} ... ok".encode() in unit_output
    integration=canonical_wire(target,env,src/PKG,wiretest,procfs_missing)
    check_files(target,test_receipt)
    check_files(target,exe_receipt)
    print("canonical-integration",tier,variant,integration,flush=True)

    tap=run(target,env,src/PKG,node,"--test","--test-reporter=tap","tests/worker.test.mjs")
    for expected in (b"# tests 12",b"# pass 12",b"# fail 0"):
        assert expected in tap,tap
    print("node-pass",tier,variant,12,flush=True)
    worker=fixtures.actual_worker(src/PKG,env,node)
    raw_wire=fixtures.worker_wire(exe,src/PKG,env)
    raw_large=fixtures.large_wire(exe,src/PKG,env,worker)
    check_files(target,exe_receipt)
    check_files(target,sdk_files)
    assert source_tree(src,omit_git=True)==before

    file=src/WORKER_RS
    initial=file.read_text()
    if variant=="stock":
        text=stock_adapter(initial)
        assert text.count("fn svg_root(")==1
    else:
        text=initial
    file.write_text(text+'\n#[cfg(test)]\n#[path = "r88_probe.rs"]\nmod r88_probe;\n')
    probe=file.parent/"r88_probe.rs"
    shutil.copyfile(HERE/"probe.rs",probe)
    reply=spool/(scope.replace("/","-")+"-worker.jsonl")
    actual=worker["flow-97"]
    assert len(json.loads(actual)["svg"].encode())>=32*1024
    reply.write_bytes(actual)
    probe_source=source_tree(src,omit_git=True)
    print("probe-source",json.dumps({"tier":tier,"variant":variant,"source_sha256":probe_source,
          "arm_source_sha256":before,"probe_sha256":hash_file(probe),"probe_worker_sha256":hash_file(file),
          "exact_real_worker_reply_sha256":hash_file(reply),"toolchain_sha256":compiler},sort_keys=True),flush=True)
    events=cargo_events(run(target,env,src,"cargo","test","--bin","mermaid-render","--no-run",*FLAGS,"--message-format=json"))
    sdk_artifact(events,"probe",probe_source)
    path,proof=binary(events,"probe",probe_source,MAIN_RS,"bin","mermaid-render",True)
    diagnostic=dict(env,R88_SVG_REPLY=str(reply))
    def measure():
        out=split_probe(run(target,diagnostic,src/PKG,path,"--exact",PROBE,"--nocapture","--test-threads=1"))
        check_files(target,proof)
        return out
    first=measure()
    assert all(measure()==first for _ in range(4))
    check_files(target,sdk_files)
    assert source_tree(src,omit_git=True)==probe_source
    return worker,raw_wire,raw_large,first,integration


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stock_git",type=Path)
    p.add_argument("m150_source",type=Path)
    p.add_argument("prior",type=Path,nargs=8)
    p.add_argument("--target",required=True,type=Path)
    p.add_argument("--lock",required=True,type=Path)
    p.add_argument("--admit-exclusive",action="store_true")
    a=p.parse_args()
    a.stock_git=a.stock_git.resolve(strict=True)
    a.m150_source=a.m150_source.resolve(strict=True)
    a.prior=[f.resolve(strict=True) for f in a.prior]
    target=a.target.resolve(strict=True)
    assert hash_file(HERE/"source.patch")==PATCH_SHA
    assert target.is_dir() and Path(os.environ["CARGO_HOME"]).is_dir()
    assert source_tree(a.m150_source)==M150 and [hash_file(f) for f in a.prior]==OVERLAYS
    print("preflight free source, target bytes",shutil.disk_usage(HERE).free,shutil.disk_usage(target).free,flush=True)
    if not a.admit_exclusive:
        print("Source/input preflight only, no compiler or worker started")
        return
    with a.lock.resolve(strict=True).open("rb") as gate:
        fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert min(shutil.disk_usage(HERE).free,shutil.disk_usage(target).free)>=512*2**20
        env=dict(os.environ,CARGO_TARGET_DIR=str(target),CARGO_NET_OFFLINE="true",CARGO_INCREMENTAL="0",
                 CARGO_BUILD_JOBS="1",TZ="UTC",LC_ALL="C",PYTHONDONTWRITEBYTECODE="1",
                 CARGO_ENCODED_RUSTFLAGS="")
        env.pop("RUSTFLAGS",None)
        env.pop("NODE_PATH",None)  # Only relative, verified packaged JS is imported.
        for var in ("RUSTC_WRAPPER","RUSTC_WORKSPACE_WRAPPER","RUSTC","NODE_OPTIONS","NODE_PATH"):
            assert not env.get(var),("unexpected tool override",var)
        chain={}
        for tool,opts in [("rustc",["-Vv"]),("cargo",["--version"]),("rustfmt",["--version"]),("node",["--version"])]:
            physical=Path(shutil.which(tool,path=env["PATH"])).resolve(strict=True)
            chain[tool]={"sha256":hash_file(physical),"version":run(target,env,HERE,physical,*opts).decode().strip()}
            if tool=="node":
                node=physical
        assert "release: 1.95.0" in chain["rustc"]["version"]
        assert int(chain["node"]["version"].split(".")[0][1:])>=20
        print("toolchain",json.dumps(chain,sort_keys=True),flush=True)
        do_not_use_basename=Path(shutil.which("node",path=env["PATH"])).resolve(strict=True)
        assert do_not_use_basename==node
        absent=scoped_procfs_probe()
        print("procfs-current-live-child", "task-children ENOENT" if absent else "child enumerated",flush=True)
        with tempfile.TemporaryDirectory(prefix="owned-svg-r88-",dir=HERE) as directory:
            prior_actual=None
            for tier in ("base","composed"):
                stock,candidate=(arm(Path(directory),tier,which,a,target,env,chain,node,absent)
                                 for which in ("stock","candidate"))
                assert stock[:3]==candidate[:3] and stock[4]==candidate[4],tier
                if prior_actual is None:
                    prior_actual=stock[:3]
                else:
                    assert prior_actual==stock[:3]
                node_ver=chain["node"]["version"]
                if node_ver=="v24.22.3":
                    assert sha256(stock[1]).hexdigest()=="2a373188cabce96b8dd182ddef7f0949f552dd159defa5cd5ecb36deb870db75"
                for name,raw in stock[0].items():
                    row=json.loads(raw)
                    print(tier,"packaged-worker",name,len(row["svg"].encode()),len(raw),sha256(raw).hexdigest(),
                          len(fixtures.diagrams()[name].encode()),row["width"],row["height"],flush=True)
                for name,raw in zip(("normal","large"),stock[1:3],strict=True):
                    print(tier,"raw-wire",name,len(raw.splitlines()),len(raw),sha256(raw).hexdigest(),flush=True)
                for label,out in zip(("stock","candidate"),(stock,candidate),strict=True):
                    for r in out[3]:
                        print(tier,"projection",label,*r,flush=True)
                validate_probe(stock[3],candidate[3])
                print(tier,"differential-pass",flush=True)
        assert source_tree(a.m150_source)==M150 and [hash_file(f) for f in a.prior]==OVERLAYS
        assert hash_file(node)==chain["node"]["sha256"]
        print("verified retained inputs and final free source, target bytes",shutil.disk_usage(HERE).free,
              shutil.disk_usage(target).free,flush=True)

if __name__=="__main__":
    main()
