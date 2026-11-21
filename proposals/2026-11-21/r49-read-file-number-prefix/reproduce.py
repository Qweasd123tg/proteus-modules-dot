#!/usr/bin/env python3
"""Compare native read_file calls; meter and latency use separate release binaries."""
import argparse, hashlib, json, os, re, shutil, statistics, subprocess as sp, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
BASE = "9469e3b12529d08b1f4a76882693e2065e842c51"
AP = argparse.ArgumentParser(description=__doc__)
AP.add_argument("repo", type=Path)
AP.add_argument("--rounds", type=int, default=9)
A = AP.parse_args()
if A.rounds < 3:
    AP.error("at least three pairs")
ARMS = ("base", "candidate")
repo = A.repo.resolve()

def build(temp, env):
    for arm in ARMS:
        tree = temp/arm
        sp.run(["git","clone","-q","--shared","--no-checkout",repo,tree],check=True)
        sp.run(["git","checkout","-q","--detach",BASE],cwd=tree,check=True)
        if arm == "candidate":
            sp.run(["git","apply","--check",HERE/"candidate.patch"],cwd=tree,check=True)
            sp.run(["git","apply",HERE/"candidate.patch"],cwd=tree,check=True)
        crate = tree/"tool/file-tools/src"
        with (crate/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r49_probe;\n")
        for mode in ("meter","clock"):
            probe=(HERE/"probe.rs").read_text()
            if mode == "clock":
                # No allocator shim, counter loads, or per-allocation hooks.
                probe=probe.replace("#[global_allocator]","#[allow(dead_code)]")
            (crate/"r49_probe.rs").write_text(probe)
            (crate/"lib.rs").touch()
            cmd=["cargo","test","--locked","--release","-p","file-tools","--lib",
                 "--no-run","--message-format=json"]
            proc=sp.run(cmd,cwd=tree,env=env,text=True,stdout=sp.PIPE)
            rows=[json.loads(x) for x in proc.stdout.splitlines()]
            if proc.returncode:
                for row in rows:
                    if row.get("reason")=="compiler-message":
                        print(row["message"].get("rendered",""))
                proc.check_returncode()
            exe,=[row["executable"] for row in rows if row.get("executable")
                  and row["target"]["name"]=="file_tools"]
            shutil.copy2(exe,temp/f"{arm}-{mode}")

def fixtures(root):
    def write(name, data):
        (root/name).write_bytes(data)
    n=60000
    short="x🙂"
    many=(short+"\r\n")*n
    write("many",many.encode())
    mixed="skip\r\nx\n\r\né🙂\rlast"
    write("mixed",mixed.encode())
    tiny=b"a\r\nb\n"
    write("tiny",tiny)
    write("empty",b"")
    write("bad",b"ok\n\xc0z\n")
    wide="".join("x\n" for _ in range(8))
    head="".join(f"{i}\tx\n" for i in range(1,9))
    filler="a"*(2*1024*1024-5-len(head)-len("9\t"))
    budget=wide+filler+"\nyZ\n"
    write("budget",budget.encode())
    def entry(label,path,opts,expected,metadata,loops):
        return (label,{"path":path,**opts},expected,metadata,loops)
    def numbered(start,end,txt):
        return "\n".join(f"{i}\t{txt}" for i in range(start,end+1))
    return [
       entry("numbered-60000","many",{"line_numbers":True},numbered(1,n,short),
             {"returned_lines":n,"total_lines":n,"scanned_bytes":len(many.encode()),"truncated":False},3),
       entry("numbered-page-100","many",{"start_line":9950,"limit":100,"line_numbers":True},
             numbered(9950,10049,short),{"returned_lines":100,"scanned_bytes":10049*len((short+"\r\n").encode()),"end_line":10049,"total_lines":None,"truncation_reason":"line_limit"},12),
       entry("numbered-small","tiny",{"line_numbers":True},"1\ta\n2\tb",
             {"returned_lines":2,"total_lines":2,"truncated":False},96),
       entry("default-small","tiny",{},tiny.decode(),
             {"total_lines":2,"returned_lines":2,"truncated":False},96),
       entry("default-60000","many",{},many,
             {"total_lines":n,"returned_lines":n,"truncated":False},4),
       entry("raw-range","mixed",{"start_line":2},"x\n\r\né🙂\rlast",
             {"returned_lines":3,"total_lines":4,"line_numbers":False},1),
       entry("numbered-empty-line-and-lone-cr","mixed",{"start_line":2,"line_numbers":True},
             "2\tx\n3\t\n4\té🙂\rlast",{"returned_lines":3,"total_lines":4,"truncated":False},1),
       entry("numbered-empty","empty",{"line_numbers":True},"",
             {"returned_lines":0,"total_lines":0,"end_line":None},1),
       entry("numbered-output-budget","budget",{"line_numbers":True},
             head+"9\t"+filler+"\n10\ty",{"returned_lines":10,"total_lines":None,
             "scanned_bytes":len(budget),"truncation_reason":"output_budget"},1),
       entry("invalid-utf8","bad",{"line_numbers":True},None,{},1),
    ]

def run():
    with tempfile.TemporaryDirectory(prefix="r49-read-") as d:
        temp=Path(d)
        work=temp/"fixture"
        work.mkdir()
        target=Path(os.getenv("CARGO_TARGET_DIR",temp/"target")).resolve()
        env={**os.environ,"CARGO_TARGET_DIR":str(target),"LC_ALL":"C"}
        build(temp,env)
        for label,request,expected,meta,loops in fixtures(work):
            output=temp/"result.json"
            invocation={**env,"R49_ARGS":json.dumps(request),"R49_CWD":str(work),"R49_OUT":str(output)}
            canon=None
            data={arm:[] for arm in ARMS}
            for mode in ("meter","clock"):
                # Meter is deterministic; rerun for each timed arm.
                n=A.rounds if mode=="clock" and loops>1 else 3
                for j in range(n):
                    for arm in (ARMS if j%2==0 else ARMS[::-1]):
                        s=sp.check_output([temp/f"{arm}-{mode}","r49_probe::full_read_invocation",
                            "--exact","--nocapture","--test-threads=1"],text=True,
                            env={**invocation,"R49_LOOPS":str(loops if mode=="clock" else 1)})
                        metrics=tuple(map(int,re.search(r"R49 (\d+) (\d+) (\d+) (\d+)",s).groups()))
                        result=output.read_bytes()
                        if canon is None:
                            canon=result
                            parsed=json.loads(result)
                            if expected is None:
                                assert parsed["ok"] is False and "invalid UTF-8" in parsed["error"],label
                            else:
                                assert parsed["ok"] is True and parsed["output"]==expected,label
                                assert parsed["metadata"]["path"]==str(work/request["path"]),label
                                assert all(parsed["metadata"][k]==v for k,v in meta.items()),label
                        assert canon==result,(label,mode,j,arm)
                        data[arm].append((mode,metrics))
            normalized=canon.replace(os.fsencode(work),b"<fixture>")
            print(f"{label}: identical full JSON; normalized SHA256 {hashlib.sha256(normalized).hexdigest()}")
            for arm in ARMS:
                meters=[row[:3] for mode,row in data[arm] if mode=="meter"]
                clocks=[row[3] for mode,row in data[arm] if mode=="clock"]
                print(f" {arm}: requested/calls/peak {meters}; raw ns/invoke {clocks}; median ns {statistics.median(clocks)}")
if __name__=="__main__":
    run()
