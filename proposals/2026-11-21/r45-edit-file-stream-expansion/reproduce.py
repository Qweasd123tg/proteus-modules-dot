#!/usr/bin/env python3
"""Run real file-tools edit_file on a disposable fixture; paired wall-time and process high-water RSS."""
import argparse, hashlib, json, os, re, resource, shutil, signal, statistics, subprocess as sp, tempfile
from pathlib import Path

BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
HERE = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repo", type=Path)
p.add_argument("--local-compiler", type=Path, help="optional optimized rustc wrapper: LIB_RS OUTPUT")
p.add_argument("--rounds", type=int, default=7)
args = p.parse_args()
if args.rounds < 2:
    p.error("--rounds must be at least 2")
repo = args.repo.resolve()
arms = ("base", "candidate")

def sig_limit(limit):
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))

with tempfile.TemporaryDirectory(prefix="r45-edit-") as td:
    t = Path(td)
    workspace = t/"workspace"
    workspace.mkdir()
    for arm in arms:
        out = t/arm
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, out], check=True)
        if args.local_compiler:
            sp.run(["git","sparse-checkout","set","tool/file-tools"], cwd=out, check=True)
        sp.run(["git","checkout","-q","--detach",BASE], cwd=out, check=True)
        if arm == "candidate":
            sp.run(["git","apply","--check",HERE/"candidate.patch"], cwd=out, check=True)
            sp.run(["git","apply",HERE/"candidate.patch"], cwd=out, check=True)
        crate = out/"tool/file-tools/src"
        shutil.copyfile(HERE/"probe.rs", crate/"tests/r45_probe.rs")
        with (crate/"tests.rs").open("a") as f:
            f.write("\nmod r45_probe;\n")
        exe = t/f"exe-{arm}"
        if args.local_compiler:
            sp.run([args.local_compiler.resolve(),crate/"lib.rs",exe], check=True)
        else:
            target = Path(os.environ.get("CARGO_TARGET_DIR", t/"target")).resolve()/f"r45-file-tools-{arm}"
            cmd = ["cargo","test","--release","--locked","-p","file-tools","--lib","--no-run","--message-format=json"]
            log = sp.check_output(cmd, cwd=out, env={**os.environ,"CARGO_TARGET_DIR":str(target)}, text=True)
            artifacts = [rec["executable"] for rec in map(json.loads, log.splitlines()) if
                         rec.get("executable") and rec["target"]["name"]=="file_tools"]
            assert len(artifacts)==1, artifacts
            shutil.copy2(artifacts[0],exe)
    def run(arm, data, old, new, all_, limit=False):
        path = workspace/"file.txt"
        path.write_bytes(data)
        params = dict(path="file.txt",old_string=old,new_string=new,replace_all=all_)
        env = {**os.environ, "R45_WORKSPACE":str(workspace),"R45_ARGS":json.dumps(params)}
        stdout = sp.check_output([t/f"exe-{arm}","tests::r45_probe::edit_fixture","--exact","--nocapture",
                                  "--test-threads=1"],text=True,env=env,preexec_fn=(lambda: sig_limit(limit)) if limit else None)
        m = re.search(r"R45 (\d+) (\d+) (\{[^\n]+\})",stdout)
        assert m,stdout
        result=json.loads(m[3])
        assert list(workspace.iterdir())==[path],list(workspace.iterdir())
        actual=path.read_bytes()
        if limit:
            assert not result["ok"] and "failed to write" in result["error"],result
            assert actual==data
        else:
            expected=data.replace(old.encode(),new.encode()) if all_ else data.replace(old.encode(),new.encode(),1)
            assert actual==expected and result["ok"],result
            assert result["metadata"]["bytes_written"]==len(actual)
            assert result["metadata"]["replacements"]==data.count(old.encode())
        return int(m[1]),int(m[2]),hashlib.sha256(actual).hexdigest(),result

    for cap,data,old,new,label in [
        (16384,b"a"*8192,"a","x"*32,"partial expanded stage"),
        (512,b"p"*1000+b"x","x","new","buffer-only final flush"),
        (1024,b"a"*8192,"a","b","nonexpanding replacement"),
    ]:
        failure=[run(a,data,old,new,True,limit=cap) for a in arms]
        assert failure[0][2:]==failure[1][2:]
        print(f"{label}, RLIMIT_FSIZE {cap}: identical failure, original intact, no temporary sibling.")

    cases=[
        ("dense-expand-32MiB",b"key=?\r\n"*65536,"?","x"*512,True),
        ("many-same-width",b"key=?\r\n"*65536,"?","!",True),
        ("single-near-end",b"body\n"*390000+b"replace!\n","replace!","done",False),
        ("small-single",b"body\n"*700+b"replace!\n","replace!","done",False),
    ]
    for name,data,old,new,all_ in cases:
        samples = {a:[] for a in arms}
        for i in range(-1,args.rounds):
            pair=[(a,run(a,data,old,new,all_)) for a in (arms if i%2==0 else arms[::-1])]
            assert pair[0][1][2:]==pair[1][1][2:]
            if i>=0:
                for a,r in pair:
                    samples[a].append(r[:2])
        print(name, "input",len(data),"output",r[3]["metadata"]["bytes_written"],"sha256",r[2])
        for a in arms:
            ns,rss=zip(*samples[a])
            print(f"  {a}: median {statistics.median(ns)/1e6:.3f} ms, {statistics.median(rss):g} KiB; samples(ns,KiB) {samples[a]}")
