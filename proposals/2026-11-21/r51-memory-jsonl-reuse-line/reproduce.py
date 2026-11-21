#!/usr/bin/env python3
"""Compare complete native recall calls with exact stock; locked release binaries."""
import argparse, hashlib, json, os, re, shutil, statistics, subprocess as sp, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("repo", type=Path)
parser.add_argument("--rounds", type=int, default=9)
args = parser.parse_args()
if args.rounds < 3:
    parser.error("at least three pairs")
ARMS = ("base", "candidate")

def build(temp, env):
    for arm in ARMS:
        tree = temp / arm
        sp.run(["git", "clone", "-q", "--shared", "--no-checkout", args.repo.resolve(), tree], check=True)
        sp.run(["git", "checkout", "-q", "--detach", BASE], cwd=tree, check=True)
        if arm == "candidate":
            sp.run(["git", "apply", "--check", HERE/"candidate.patch"], cwd=tree, check=True)
            sp.run(["git", "apply", HERE/"candidate.patch"], cwd=tree, check=True)
        crate = tree/"context_provider/memory-pack/src"
        with (crate/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r51_probe;\n")
        for mode in ("meter", "clock"):
            probe = (HERE/"probe.rs").read_text()
            if mode == "clock":
                # No allocator shim in these timing binaries.
                probe = probe.replace("#[global_allocator]", "#[allow(dead_code)]")
            (crate/"r51_probe.rs").write_text(probe)
            (crate/"lib.rs").touch()
            cmd = ["cargo", "test", "--locked", "--release", "-p", "memory-pack", "--lib",
                   "--no-run", "--message-format=json"]
            proc = sp.run(cmd, cwd=tree, env=env, text=True, stdout=sp.PIPE)
            rows = [json.loads(x) for x in proc.stdout.splitlines()]
            if proc.returncode:
                for row in rows:
                    if row.get("reason") == "compiler-message":
                        print(row["message"].get("rendered", ""))
                proc.check_returncode()
            exe, = [row["executable"] for row in rows if row.get("executable")
                    and row["target"]["name"] == "memory_pack"]
            shutil.copy2(exe, temp/f"{arm}-{mode}")

def fixtures(work):
    def make(name, raw):
        path = work/name
        path.write_bytes(raw)
        return path
    def fact(content, kind="fact", metadata=None):
        return {"kind":kind, "content":content, "metadata":metadata}
    def row(item, ending=b"\n"):
        return json.dumps(item, ensure_ascii=False, separators=(",",":")).encode()+ending
    any1, any2 = fact("Привет\t✨"), fact("first real match", "preference", {"labels":[1,2]})
    results = [fact(f"target {i:03d}🙂", metadata={"source":"fixture"}) for i in range(25)]
    filler = fact("ordinary-"+"x"*90, metadata={"scope":"refs","tags":["sample","test"]})
    prefix = row(filler)*60000
    large = make("large.jsonl", prefix+b"".join(map(row,results)))
    small = make("small.jsonl", row(any1, b"\r\n")+row(any2, b""))
    outlier = make("outlier.jsonl", row(fact("a"*1024*1024),b"\r\n")+row(filler)*1000+row(any2,b"\r"))
    broken = make("broken.jsonl", row(any1,b"\n")+b"}\r\n"+row(any2))
    invalid = make("invalid.jsonl", row(any1)+b"\xff\r\n")
    blank = make("blank.jsonl", b"\r\n"+row(any1))
    return [
      ("large-filter",large,{"query":"target","limit":3},results[:3],2,False),
      ("large-miss",large,{"query":"missing","limit":1},[],2,False),
      ("default-first-20",large,{"query":""},[filler]*20,45,False),
      ("small-mixed-eol",small,{"query":""},[any1,any2],80,False),
      ("outlier-then-match",outlier,{"query":"match"},[any2],2,False),
      ("provider-search",small,{"query":"match","limit":2},[any2],1,True),
      ("provider-error",broken,{"query":"nomatch"},"line 2",1,True),
      ("malformed-json",broken,{"query":""},"line 2",1,False),
      ("truncated-on-limit",broken,{"query":"","limit":1},[any1],1,False),
      ("invalid-utf8",invalid,{"query":""},"valid UTF-8",1,False),
      ("empty-line",blank,{"query":""},"line 1",1,False),
      ("missing-file",work/"missing.jsonl",{"query":""},[],1,False),
      ("zero-before-read",invalid,{"query":"","limit":0},[],1,False),
    ]

def verify(raw, expected, provider):
    if isinstance(expected, str):
        assert raw.startswith(b"ERROR: ") and expected.encode() in raw,raw
    else:
        assert not raw.startswith(b"ERROR: "),raw
        parsed = json.loads(raw)
        if provider:
            assert len(parsed)==len(expected),parsed
            for got,item in zip(parsed,expected):
                assert (got["source"],got["content"],got["metadata"]) == (
                  "memory:"+item["kind"],item["content"],item["metadata"]),got
        else:
            assert parsed["ok"] is True,parsed
            if expected:
                assert parsed["metadata"]["items"]==expected,parsed
                assert parsed["output"]=="\n".join(f'{i["kind"]}: {i["content"]}' for i in expected),parsed
            else:
                assert parsed["output"]=="(no memories)",parsed

with tempfile.TemporaryDirectory(prefix="r51-memory-pack-") as d:
    temp = Path(d)
    work = temp/"fixture"
    work.mkdir()
    target = Path(os.getenv("CARGO_TARGET_DIR",temp/"target")).resolve()
    env = {**os.environ,"CARGO_TARGET_DIR":str(target),"LC_ALL":"C"}
    env.pop("R51_PROVIDER",None)
    build(temp,env)
    for label,path,request,expected,loops,provider in fixtures(work):
        output = temp/"result"
        invocation = {**env,"R51_ARGS":json.dumps(request),"R51_PATH":str(path),"R51_OUT":str(output)}
        if provider:
            invocation["R51_PROVIDER"]="1"
        canon = None
        data = {arm:[] for arm in ARMS}
        for mode in ("meter","clock"):
            n = args.rounds if mode=="clock" and loops>1 else 3
            for j in range(n):
                for arm in (ARMS if j%2==0 else ARMS[::-1]):
                    s = sp.check_output([temp/f"{arm}-{mode}","r51_probe::full_recall_invocation",
                        "--exact","--nocapture","--test-threads=1"],text=True,
                        env={**invocation,"R51_LOOPS":str(loops if mode=="clock" else 1)})
                    metrics = tuple(map(int,re.search(r"R51 (\d+) (\d+) (\d+) (\d+)",s).groups()))
                    raw = output.read_bytes()
                    if canon is None:
                        canon = raw
                        verify(canon,expected,provider)
                    assert raw==canon,(label,mode,j,arm)
                    data[arm].append((mode,metrics))
        normalized = canon.replace(os.fsencode(work),b"<fixture>")
        print(f"{label}: byte-exact; normalized SHA256 {hashlib.sha256(normalized).hexdigest()}")
        for arm in ARMS:
            met = [row[:3] for mode,row in data[arm] if mode=="meter"]
            clk = [row[3] for mode,row in data[arm] if mode=="clock"]
            print(f" {arm}: requested/calls/peak {met}; raw ns/invoke {clk}; median ns {statistics.median(clk)}")
