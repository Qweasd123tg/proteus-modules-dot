#!/usr/bin/env python3
"""Alternate stock/candidate invocations of the real sqlite-memory exports."""
import argparse, hashlib, json, os, re, shutil, statistics, subprocess as sp, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repo", type=Path)
p.add_argument("--rounds", type=int, default=9)
p.add_argument("--label", default="release")
args = p.parse_args()
if args.rounds < 3:
    p.error("use at least three rounds")
repo = args.repo.resolve()
arms = ("base", "candidate")
with tempfile.TemporaryDirectory(prefix="r46-sqlite-memory-") as td:
    tmp = Path(td)
    target = Path(os.environ.get("CARGO_TARGET_DIR", tmp/"target")).resolve()
    for arm in arms:
        tree = tmp / arm
        sp.run(["git","clone","-q","--shared","--no-checkout",repo,tree],check=True)
        sp.run(["git","checkout","--detach","-q",BASE],cwd=tree,check=True)
        if arm == "candidate":
            sp.run(["git","apply","--check",HERE/"candidate.patch"],cwd=tree,check=True)
            sp.run(["git","apply",HERE/"candidate.patch"],cwd=tree,check=True)
        crate = tree/"context_provider/sqlite-memory/src"
        shutil.copyfile(HERE/"probe.rs", crate/"tests/r46_probe.rs")
        with (crate/"lib.rs").open("a") as f:
            f.write('\n#[cfg(test)]\nmod r46_bench_tests {\n    use super::*;\n    #[path = "../tests/r46_probe.rs"]\n    mod bench;\n    fn fresh_conn() -> Mutex<Connection> {\n        let conn = Connection::open_in_memory().unwrap();\n        conn.execute_batch(SCHEMA).unwrap();\n        Mutex::new(conn)\n    }\n}\n')
        # Have the test harness load the probe from its logical parent directory.
        (crate/"r46_bench_tests").mkdir(exist_ok=True)
        cmd = ["cargo","test","--locked","--release","-p","sqlite-memory","--lib","--no-run","--message-format=json"]
        build = sp.run(cmd, cwd=tree, env={**os.environ,"CARGO_TARGET_DIR":str(target)},
                       text=True, stdout=sp.PIPE)
        messages = [json.loads(row) for row in build.stdout.splitlines()]
        if build.returncode:
            for message in messages:
                if message.get("reason") == "compiler-message":
                    print(message["message"].get("rendered", ""), file=sys.stderr)
            build.check_returncode()
        artifacts = [v["executable"] for v in messages if
                     v.get("executable") and v["target"]["name"] == "sqlite_memory"]
        assert len(artifacts)==1,artifacts
        shutil.copy2(artifacts[0],tmp/f"{arm}.exe")

    print(args.label, "Cargo release, real SQLite (in memory). Nanoseconds/invocation.")
    for case in ("remember","recent","fts_tool","fts_provider"):
        samples={a:[] for a in arms}
        canonical = None
        for i in range(-1, args.rounds):
            for a in (arms if i%2==0 else arms[::-1]):
                out = tmp/"output.jsonl"
                call = [tmp/f"{a}.exe","r46_bench_tests::bench::time_real_surfaces",
                        "--exact","--nocapture","--test-threads=1"]
                log = sp.check_output(call,text=True,env={**os.environ,"R46_OUTPUT":str(out),"R46_CASE":case})
                m = re.search(r"R46 (\d+) (\d+)",log)
                assert m,log
                body = out.read_bytes()
                if canonical is None:
                    canonical = body
                assert body==canonical, (case,a,i)
                count = int(m[2])
                if i >= 0:
                    samples[a].append(round(int(m[1])/count,1))
        print(f"{case} replies={canonical.count(bytes([10]))+1} sha256={hashlib.sha256(canonical).hexdigest()}")
        for a in arms:
            print(a, "median", statistics.median(samples[a]), samples[a])
