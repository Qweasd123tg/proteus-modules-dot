#!/usr/bin/env python3
"""Compare stock and candidate SkillTool handlers over real catalog files."""
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
ARMS = ("base","candidate")

def build(temp,env):
    for arm in ARMS:
        tree=temp/arm
        sp.run(["git","clone","-q","--shared","--no-checkout",args.repo.resolve(),tree],check=True)
        sp.run(["git","checkout","-q","--detach",BASE],cwd=tree,check=True)
        if arm=="candidate":
            sp.run(["git","apply","--check",HERE/"candidate.patch"],cwd=tree,check=True)
            sp.run(["git","apply",HERE/"candidate.patch"],cwd=tree,check=True)
        crate=tree/"tool/skill-pack/src"
        with (crate/"lib.rs").open("a") as f:
            f.write("\n#[cfg(test)]\nmod r54_probe;\n")
        for mode in ("meter","clock"):
            probe=(HERE/"probe.rs").read_text()
            if mode=="clock":
                probe=probe.replace("#[global_allocator]","#[allow(dead_code)]")
            (crate/"r54_probe.rs").write_text(probe)
            (crate/"lib.rs").touch()
            cmd=["cargo","test","--locked","--release","-p","skill-pack","--lib",
                 "--no-run","--message-format=json"]
            proc=sp.run(cmd,cwd=tree,env=env,text=True,stdout=sp.PIPE)
            rows=[json.loads(x) for x in proc.stdout.splitlines()]
            if proc.returncode:
                for row in rows:
                    if row.get("reason")=="compiler-message":
                        print(row["message"].get("rendered",""))
                proc.check_returncode()
            exe,=[row["executable"] for row in rows if row.get("executable") and
                  row["target"]["name"]=="skill_pack"]
            target=temp/f"{arm}-{mode}"
            shutil.copy2(exe,target)
            assert "r54_probe::skill_invocation: test" in sp.check_output([target,"--list"],text=True)

def setup(root):
    for name in ("big","small","single","invalid","oversize","plugins",
                 "override","user-override","user-empty", "kit","kit-extra","kit-malformed"):
        (root/name).mkdir()
    for name in ("big","small","single","invalid","oversize","plugins","override"):
        (root/name/".git").mkdir()
    def write(folder,name,body,header=None):
        directory=folder/name
        directory.mkdir(parents=True,exist_ok=True)
        record=(header or f"---\nname: {name}\ndescription: Test skill {name}\n---\n\n").encode()+body
        (directory/"SKILL.md").write_bytes(record)
    targets={}
    for name,count,body_size in (("big",96,128*1024),("small",8,3072),("single",1,3072)):
        project=root/name/".proteus/skills"
        for i in range(count):
            skill=f"entry-{i:03d}"
            phrase=f"Fixture {skill}🙂 ".encode()
            body=phrase*(body_size//len(phrase))
            write(project,skill,body+b"\n")
            if i==count//2:
                targets[name]=(skill,body.decode().strip())
    for project in ("invalid","oversize","override","plugins"):
        write(root/project/".proteus/skills","review",b"   project body\n")
    write(root/"user-override/skills","review",b"user body\n")
    write(root/"invalid/.proteus/skills","z-other",b"\xff")
    write(root/"oversize/.proteus/skills","z-other",b"x"*(256*1024+1))
    write(root/"kit/skills","review",b"wrong plugin")
    write(root/"kit-extra/skills","review","wanted 🙂\n".encode())
    write(root/"kit-extra/skills","testing",b"unrelated plugin body")
    write(root/"kit-malformed/skills","review",b"\xff")
    def request(label,ws,name,body,loops=1,source="project",error=None,
                disabled=(),packages=(),home="user-empty",provider=False):
        return (label,{"cwd":str(root/ws),"name":name,"provider":provider,
                    "settings":{"disabled":list(disabled),
                      "packages":[{"id":prefix,"root":str(root/folder),"enabled":enabled}
                                  for prefix,folder,enabled in packages]}},
                root/home,body,source,error,loops)
    pkgs=[("kit","kit",True),("kit:extra","kit-extra",True),
          ("invalid-package","kit-malformed",True)]
    return [
        request("many-large","big",*targets["big"],loops=3),
        request("eight-small","small",*targets["small"],loops=30),
        request("single-small","single",*targets["single"],loops=70),
        request("many-missing","big","not-present",None,loops=2,error="is not available"),
        request("plugin-prefix","plugins","kit:extra:review","wanted 🙂",source="plugin",packages=pkgs),
        request("plugin-disabled","plugins","kit:extra:review",None,
                error="is not available",disabled=["kit:extra:review"],packages=pkgs),
        request("project-overrides","override","review","project body",home="user-override"),
        request("other-invalid-utf8","invalid","review",None,error="not UTF-8"),
        request("other-over-size","oversize","review",None,error="exceeds 262144 bytes"),
        request("provider-control","small","unused",None,loops=18,provider=True),
    ]

def verify(raw,fixture,expected,source,error):
    reply=json.loads(raw)
    if fixture["provider"]:
        assert len(reply)==1 and reply[0]["metadata"]["skill_count"]==8
        assert reply[0]["content"].count("<skill>\n")==8 and "Fixture entry" not in reply[0]["content"]
    elif error:
        assert reply["ok"] is False and reply["output"]=="" and error in reply["error"],reply
    else:
        assert reply["ok"] is True and reply["output"]==expected,reply
        assert reply["metadata"]["source"]==source and reply["metadata"]["tool"]=="skill",reply
        assert reply["metadata"]["name"]==fixture["name"].split(":")[-1]

with tempfile.TemporaryDirectory(prefix="r54-skill-pack-") as d:
    temp=Path(d)
    root=temp/"fixture"
    root.mkdir()
    target=Path(os.getenv("CARGO_TARGET_DIR",temp/"target")).resolve()
    env={**os.environ,"CARGO_TARGET_DIR":str(target),"LC_ALL":"C"}
    build(temp,env)
    for label,fixture,home,body,source,error,loops in setup(root):
        out=temp/"result"
        f=temp/"fixture.json"
        f.write_text(json.dumps(fixture))
        invocation={**env,"R54_FIXTURE":str(f),"R54_OUT":str(out),"PROTEUS_HOME":str(home)}
        canon=None
        data={arm:[] for arm in ARMS}
        for mode in ("meter","clock"):
            n=args.rounds if mode=="clock" and loops>1 else 3
            for j in range(n):
                for arm in (ARMS if j%2==0 else ARMS[::-1]):
                    s=sp.check_output([temp/f"{arm}-{mode}","r54_probe::skill_invocation",
                        "--exact","--nocapture","--test-threads=1"],text=True,
                        env={**invocation,"R54_LOOPS":str(loops if mode=="clock" else 1)})
                    m=re.search(r"R54 (\d+) (\d+) (\d+) (\d+)",s)
                    assert m,s
                    metrics=tuple(map(int,m.groups()))
                    raw=out.read_bytes()
                    if canon is None:
                        canon=raw
                        verify(canon,fixture,body,source,error)
                    assert raw==canon,(label,mode,j,arm)
                    data[arm].append((mode,metrics))
        normalized=canon.replace(os.fsencode(root),b"<fixture>")
        print(f"{label}: byte-exact response; normalized SHA256 {hashlib.sha256(normalized).hexdigest()}")
        for arm in ARMS:
            met=[row[:3] for mode,row in data[arm] if mode=="meter"]
            clk=[row[3] for mode,row in data[arm] if mode=="clock"]
            print(f" {arm}: requested/calls/peak {met}; raw ns/invoke {clk}; median ns {statistics.median(clk)}")
