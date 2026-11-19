"""Reproduce from a clean pinned Extensions checkout on Linux; no private fixtures."""
from pathlib import Path
import sys, shutil, subprocess, os
source, out = (Path(s).resolve() for s in sys.argv[1:3])
here = Path(__file__).resolve().parent
out.mkdir(parents=True,exist_ok=False)
for variant in ('base','after'):
    v=out/variant
    shutil.copytree(source, v, ignore=shutil.ignore_patterns('.git','target','build'), symlinks=True)
    if variant=='after':
        subprocess.run(['git','apply',str(here/'move-widget-arrays.patch')],cwd=v,check=True)
    main=v/'packages/files/src/main.rs'
    s=main.read_text(); assert s.count('fn main() {')==1
    main.write_text(s.replace('fn main() {','#[allow(dead_code)] fn shipped_main() {')+'\n'+(here/'panel_probe.rs').read_text())
    for name,flags in [('time',[]),('heap',['--cfg','heap_probe'])]:
        target=out/f'target-{variant}'
        subprocess.run(['cargo','rustc','--release','--locked','-p','extension-files','--bin','files','--',*flags],cwd=v,env={**os.environ,'CARGO_TARGET_DIR':str(target)},check=True)
        shutil.copy2(target/'release/files',v/name)
subprocess.run([sys.executable,str(here/'measure.py'),str(out),*sys.argv[3:]],cwd=out,check=True)
