"""Compile the exact before/after TurnProgress modules and their unit tests with one built dependency set."""
from pathlib import Path
import shutil, subprocess as sp, sys, tempfile

repo, deps = (Path(arg).resolve() for arg in sys.argv[1:])
here = Path(__file__).resolve().parent
base = "32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f"
app = Path("crates/proteus-core/src/app_server")
src = app / "turn_progress"
def git(*cmd):
    return sp.check_output(["git","-C",repo,*cmd])
def put(p, b):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(b)
with tempfile.TemporaryDirectory() as temp:
    t = Path(temp)
    tree = t/"source"
    tree.mkdir()
    sp.run(["git","init","-q"],cwd=tree,check=True)
    files = [Path(p) for p in git("ls-tree","-r","--name-only",base,"--",str(src),str(src.with_suffix(".rs"))).decode().splitlines()]
    for p in files:
        b = git("show",f"{base}:{p}")
        put(tree/p,b)
        put(t/"baseline"/p.relative_to(app),b)
    sp.run(["git","apply","--check",here/"source.patch"],cwd=tree,check=True)
    sp.run(["git","apply","--whitespace=error",here/"source.patch"],cwd=tree,check=True)
    for p in files:
        put(t/"candidate"/p.relative_to(app),(tree/p).read_bytes())
    put(t/"test_alloc.rs",git("show",f"{base}:crates/proteus-contracts/src/test_alloc.rs"))
    shutil.copyfile(here/"probe.rs",t/"probe.rs")
    cmd = ["rustc","--edition=2024","--test","-Adead_code","-Copt-level=2","-Cdebuginfo=0",
           "-Cstrip=symbols","-Clink-arg=-fuse-ld=lld","-L",f"dependency={deps}"]
    for name in ["bytes","proteus_contracts","serde_json","uuid"]:
        libs = list(deps.glob(f"lib{name}-*.rlib"))
        if len(libs)!=1:
            raise ValueError(f"one coherent set of built dependencies required: {name}: {libs}")
        cmd+=["--extern",f"{name}={libs[0]}"]
    sp.run(cmd+["probe.rs","-o","probe"],cwd=t,check=True)
    sp.run([t/"probe","--test-threads=1","--nocapture"],cwd=t,check=True)
