#!/usr/bin/env python3
"""Compare find_files allocation traffic and actual ripgrep output."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess as sp
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("repo", type=Path)
p.add_argument("--rounds", type=int, default=9)
args = p.parse_args()
if args.rounds < 3:
    p.error("use at least three pairs")
repo = args.repo.resolve()
arms = ("base", "candidate")

def build_both(temp, env):
    for arm in arms:
        tree = temp / arm
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, tree], check=True)
        sp.run(["git", "checkout", "-q", "--detach", BASE], cwd=tree, check=True)
        if arm == "candidate":
            sp.run(["git", "apply", "--check", HERE/"candidate.patch"], cwd=tree, check=True)
            sp.run(["git", "apply", HERE/"candidate.patch"], cwd=tree, check=True)
        crate = tree/"tool/file-tools/src"
        shutil.copyfile(HERE/"probe.rs", crate/"r48_probe.rs")
        with (crate/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r48_probe;\n")
        cmd = ["cargo", "test", "--locked", "--release", "-p", "file-tools", "--lib", "--no-run",
               "--message-format=json"]
        proc = sp.run(cmd, cwd=tree, env=env, text=True, stdout=sp.PIPE)
        messages = [json.loads(row) for row in proc.stdout.splitlines()]
        if proc.returncode:
            for m in messages:
                if m.get("reason") == "compiler-message":
                    print(m["message"].get("rendered", ""), file=sys.stderr)
            proc.check_returncode()
        exes = [m["executable"] for m in messages if
                m.get("executable") and m["target"]["name"] == "file_tools"]
        assert len(exes) == 1, exes
        shutil.copy2(exes[0], temp/f"{arm}.exe")

def fixtures(root):
    dirs = {}
    for key in ("many", "some", "odd", "empty", "invalid"):
        dirs[key] = root/key
        dirs[key].mkdir()
    inner = dirs["many"]
    for i in range(4):
        inner = inner / (f"catalog{i}-" + "segment"*14)
        inner.mkdir()
    for i in range(1130):
        (inner/(f"index-{i:04}-" + "abcdef"*15 + ".rs")).touch()
    for name in ("one.rs", "путь.rs", "three.rs", "ignored.tmp.rs"):
        (dirs["some"]/name).touch()
    for name in ("returns\rhere.txt", "line\nbreak.txt", "ends-with-CR\r", "✨-plane.txt"):
        (dirs["odd"]/name).touch()
    fd = os.open(os.fsencode(dirs["invalid"]) + b"/raw-\xff.txt", os.O_CREAT|os.O_EXCL, 0o600)
    os.close(fd)
    return [
        ("capped-long-paths", {"path":"many","pattern":"**/*.rs","max_results":10000}),
        ("root-default-limit", {"pattern":"**/*.rs"}),
        ("small-scoped", {"path":"some","pattern":"**/*.rs","exclude":["*.tmp.rs"]}),
        ("exact-limit", {"path":"some","pattern":"**/*.rs","exclude":["*.tmp.rs"],"max_results":3}),
        ("odd-filenames", {"path":"odd","pattern":"*"}),
        ("empty", {"path":"empty","pattern":"**/*.rs"}),
        ("invalid-utf8", {"path":"invalid","pattern":"*"}),
    ]

def reference(label, req, root, env):
    opts = ["--files", "--glob", req["pattern"]]
    for glob in req.get("exclude",[]):
        opts += ["--glob", "!"+glob]
    raw=sp.run(["rg", *opts, "--", req.get("path", ".")],cwd=root,env=env,capture_output=True)
    assert raw.returncode in (0,1),raw.stderr
    if label=="invalid-utf8":
        assert b"\xff" in raw.stdout,raw.stdout
        return None
    # BufRead::lines discards each LF and a CR immediately before that LF.
    parts=raw.stdout.split(b"\n")
    lines=[line.removesuffix(b"\r") for line in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    cap=min(req.get("max_results",100),1000)
    lines=lines[:cap]
    rendered=[p.removeprefix(b"./").decode("utf-8") for p in lines]
    return ("\n".join(rendered) if rendered else "(no matches)",len(rendered),cap)

with tempfile.TemporaryDirectory(prefix="r48-find-files-") as td:
    temp=Path(td)
    work=temp/"fixture"
    work.mkdir()
    config=temp/"rg.conf"
    # Scheduling and directory walking are not part of this comparison.
    config.write_text("--threads=1\n")
    target=Path(os.environ.get("CARGO_TARGET_DIR",temp/"target")).resolve()
    env={**os.environ, "CARGO_TARGET_DIR":str(target),"RIPGREP_CONFIG_PATH":str(config),"LC_ALL":"C"}
    build_both(temp,env)
    for label, req in fixtures(work):
        ref=reference(label,req,work,env)
        out=temp/"result.json"
        invocation={**env,"R48_CWD":str(work),"R48_ARGS":json.dumps(req),"R48_OUT":str(out)}
        canonical=None
        samples={a:[] for a in arms}
        for lap in range(-1,args.rounds):
            for a in (arms if lap%2==0 else arms[::-1]):
                log=sp.check_output([temp/f"{a}.exe","r48_probe::measure_find_files",
                                     "--exact","--nocapture","--test-threads=1"],
                                    env=invocation,text=True)
                m=re.search(r"R48 (\d+) (\d+) (\d+)",log)
                assert m,log
                result=out.read_bytes()
                if canonical is None:
                    canonical=result
                    parsed=json.loads(result)
                    if ref is None:
                        assert parsed["ok"] is False and "UTF-8" in parsed["error"],parsed
                    else:
                        output,count,cap=ref
                        assert parsed["ok"] is True and parsed["output"]==output,label
                        meta=parsed["metadata"]
                        assert meta["match_count"]==count and meta["max_results"]==cap,meta
                        assert meta["truncated"]==(count>=cap),meta
                        assert meta["exclude"]==req.get("exclude",[]) and meta["pattern"]==req["pattern"],meta
                        assert meta["path"]==str(work/req.get("path",".")),meta
                        if label=="capped-long-paths":
                            assert count==1000 and len(output)>=400000
                        if label=="odd-filenames":
                            assert "line\nbreak.txt" in output and "returns\rhere.txt" in output
                        if label=="exact-limit":
                            assert count==3 and meta["truncated"]
                assert result==canonical,(label,a,lap)
                if lap>=0:
                    samples[a].append(tuple(map(int,m.groups())))
        # Verify raw replies above; replace only the known temporary root for
        # stable, shareable hashes across independently recreated fixtures.
        normalized=canonical.replace(os.fsencode(work),b"<fixture>")
        print(f"{label}: byte-identical JSON; normalized SHA256 {hashlib.sha256(normalized).hexdigest()}")
        for a in arms:
            med=tuple(statistics.median(series) for series in zip(*samples[a]))
            print(f" {a} median requested bytes/alloc calls/ns {med}; raw {samples[a]}")
