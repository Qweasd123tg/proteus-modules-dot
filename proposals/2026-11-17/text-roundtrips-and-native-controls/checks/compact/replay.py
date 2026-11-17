"""Offline reproduction. Requires rustc, Python 3, and compatible, already built serde(derive)/serde_json rlibs."""
import argparse, hashlib, shutil, subprocess, sys, tempfile
from pathlib import Path

def blob(path):
    b=path.read_bytes()
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def resolve_rlib(deps,stem,override):
    if override: return override.resolve(strict=True)
    hits=list(deps.glob('lib'+stem+'-*.rlib'))
    if len(hits)!=1:
        raise SystemExit(f'Expected one {stem} .rlib in {deps}, found {len(hits)}. Set --{stem.replace("_","-")} explicitly.')
    return hits[0].resolve()

ap=argparse.ArgumentParser(description=__doc__)
for name in ['core','desktop','candidate','deps']:ap.add_argument('--'+name,type=Path,required=True)
for name in ['serde','serde-json','evidence']:ap.add_argument('--'+name,type=Path)
ap.add_argument('--rustc',default='rustc')
a=ap.parse_args(); deps=a.deps.resolve(strict=True)
rustc=shutil.which(a.rustc)
if not rustc: raise SystemExit('rustc not found')
rustc=str(Path(rustc).absolute())
serde=resolve_rlib(deps,'serde',a.serde); js=resolve_rlib(deps,'serde_json',a.serde_json)
desktop=Path('src/settings/schema.rs'); core=Path('crates/proteus-contracts/src/domain/config_schema.rs')
if blob(a.desktop/desktop)!='1a799115bf45e9854defbc3b0c4f4cc6645e4a2c':raise SystemExit('Unexpected base Desktop formatter')
if blob(a.core/core)!='5c1cb74d5d7afc957c05165c1b916019529a5129':raise SystemExit('Unexpected base Core schema')
src=(a.core/core).read_text()
begin=src.index('use serde::{Deserialize, Serialize};'); end=src.index('\nimpl ModuleConfigSchema {',begin)
here=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as tmp:
    w=Path(tmp)
    for d in ['harness','before','after','evidence']:(w/d).mkdir()
    for f in ['probe.rs','check.py','build.py']:shutil.copyfile(here/f,w/'harness'/f)
    (w/'harness/core_types.rs').write_text(src[begin:end])
    for d,x in [('before',a.desktop/desktop),('after',a.candidate/desktop)]:shutil.copyfile(x,w/d/'schema.rs')
    subprocess.run([sys.executable,'harness/build.py',rustc,str(deps),str(serde),str(js)],cwd=w,check=True)
    p=subprocess.run([sys.executable,'harness/check.py','./before/probe','./after/probe'],cwd=w,capture_output=True,text=True)
    if p.returncode:sys.stderr.write(p.stderr);raise SystemExit(p.returncode)
    (w/'evidence/structural.log').write_text(p.stdout)
    print(p.stdout,end='')
    if a.evidence:
        a.evidence.mkdir(parents=True,exist_ok=True)
        for f in (w/'evidence').iterdir(): shutil.copyfile(f,a.evidence/f.name)
