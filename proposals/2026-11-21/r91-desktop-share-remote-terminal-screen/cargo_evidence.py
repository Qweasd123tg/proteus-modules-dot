"""Validate newly built Cargo artifacts for the exact headless fixture and local diff tests."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def inputs(root):
    files = [root/"Cargo.toml", root/"Cargo.lock", root/"crates/terminal/Cargo.toml"]
    files += sorted((root/"crates/terminal/src").rglob("*.rs"))
    files += sorted(p for p in (root/"vendor").rglob("*") if p.is_file() and not p.is_symlink())
    return {f.relative_to(root).as_posix():digest(f) for f in files}

if sys.argv[1] == "snapshot":
    print(json.dumps(inputs(Path(sys.argv[2]).resolve()),sort_keys=True))
    sys.exit(0)

mode, stamp, root, prefix, patch = sys.argv[1:]
root,prefix,patch = (Path(x).resolve() for x in (root,prefix,patch))
assert mode == "unit"
run_tests = True
name = "proteus_terminal"
manifest = "crates/terminal/Cargo.toml"
src = "crates/terminal/src/lib.rs"
kind = ["lib"]
reports = lambda suffix: Path(str(prefix)+suffix)
base = str(prefix).removesuffix("."+mode)
bound = json.loads(Path(base+".inputs").read_text())
assert bound == inputs(root)
messages = [json.loads(l) for l in reports(".cargo-json").read_text().splitlines() if l]
matches = [v for v in messages if v.get("reason") == "compiler-artifact"
    and v.get("target",{}).get("name")==name and v["target"]["kind"]==kind
    and v["profile"]["test"]==run_tests
    and Path(v["manifest_path"]).resolve()==root/manifest]
assert len(matches)==1,(stamp,mode,len(matches))
v=matches[0]
assert v["fresh"] is False and Path(v["target"]["src_path"]).resolve(strict=True)==root/src
assert [m["success"] for m in messages if m.get("reason")=="build-finished"]==[True]
binary=Path(v["executable"]).resolve(strict=True)
warm=Path(os.environ["CARGO_TARGET_DIR"]).resolve(strict=True)
recorded=binary.relative_to(warm)
if run_tests:
    assert recorded.parts[:2]==("debug","deps") and binary.name.startswith("proteus_terminal-")
else:
    raise AssertionError("unexpected non-test artifact")

pre=digest(binary)
args=[str(binary), "--test-threads=1", "--nocapture"] if run_tests else [str(binary)]
with reports(".stdout").open("wb") as out, reports(".stderr").open("wb") as err:
    result=subprocess.run(args,cwd=root,stdout=out,stderr=err)
if result.returncode:
    sys.stdout.write(reports(".stdout").read_text())
    sys.stderr.write(reports(".stderr").read_text())
    sys.exit(result.returncode)
post=digest(binary)
assert pre==post and inputs(root)==bound
lines=reports(".stdout").read_text().splitlines()
assert sum(l.startswith("test ") and not l.startswith("test result:") for l in lines)==int(next(l.split()[1] for l in lines if l.startswith("running ")))
assert ("ARM "+stamp) in lines and sum(l.startswith("TRACE ") for l in lines)==4
def tool(name):
    path=Path(shutil.which(name)).resolve(strict=True)
    return {"launcher_sha256":digest(path),"version":subprocess.check_output([str(path),"--version"],text=True).strip()}
record={"arm":stamp,"mode":mode,"fresh":False,"test":run_tests,"kind":kind,"target":name,"manifest":manifest,
    "source":src,"executable_from_warm_target":recorded.as_posix(),"executable_sha256_before":pre,
    "executable_sha256_after":post,"stdout_sha256":digest(reports(".stdout")),"source_patch_sha256":digest(patch),
    "inputs_sha256":bound,"cargo":tool("cargo"),"rustc":tool("rustc")}
print("ARTIFACT "+json.dumps(record,sort_keys=True,separators=(",",":")))
