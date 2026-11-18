"""Prepare a NEW local-only fallback project; install/fetch/run nothing."""
import argparse, json, pathlib, shutil, subprocess
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("core",type=pathlib.Path,help="existing local Core checkout at b2c285f")
p.add_argument("dest",type=pathlib.Path,help="fresh destination, must not already exist")
a=p.parse_args()
dist=pathlib.Path(__file__).resolve().parent
core=a.core.resolve()
want="b2c285fcc317379ab47e484945afb7fc2b436331"
got=subprocess.check_output(["git","-C",str(core),"rev-parse","HEAD"],text=True).strip()
if got!=want:p.error("fallback verified only at Core "+want+"; got "+got)
crate=core/"crates/proteus-module-sdk"
if not (crate/"Cargo.toml").is_file():p.error("local SDK manifest not found")
if a.dest.exists():p.error("use a new directory")
before='{ git = "https://github.com/Proteus-harness/Proteus-core.git", rev = "59da60a35929b6ab73550ee39c4f07f3bfa513a1" }'
s=(dist.parent/"word-count"/"Cargo.toml").read_text()
if s.count(before)!=1:p.error("unexpected source manifest; refusing replacement")
a.dest.mkdir(parents=True)
shutil.copytree(dist.parent/"word-count"/"src", a.dest/"src")
shutil.copy2(dist.parent/"word-count"/"rust-toolchain.toml", a.dest/"rust-toolchain.toml")
(a.dest/"Cargo.toml").write_text(s.replace(before,"{ path = "+json.dumps(str(crate),ensure_ascii=False)+" }"))
shutil.copy2(dist/"Cargo.lock",a.dest/"Cargo.lock")
print("Prepared local-SDK copy; no dependencies fetched and no programs started.")
