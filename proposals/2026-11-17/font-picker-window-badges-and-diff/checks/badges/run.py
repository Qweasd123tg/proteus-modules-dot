from pathlib import Path
import subprocess as s, sys, tempfile
here=Path(__file__).resolve().parent
if len(sys.argv)!=3: raise SystemExit('run.py BASE_DESKTOP PATCHED_DESKTOP')
roots={'base':Path(sys.argv[1]).resolve(),'after':Path(sys.argv[2]).resolve()}
rustc='rustc'
with tempfile.TemporaryDirectory() as directory:
 tmp=Path(directory)
 for variant in ('base','after'):
  harness=(here/'driver.rs.in').read_text().replace('@ARRANGE@',str(roots[variant]/'src/ui/badges/arrange.rs')).replace('@ORDER@',str(here/'saved-order.inc'))
  _,path=variant,tmp/'driver.rs'
  path.write_text(harness)
  cfg=['--cfg','candidate'] if variant=='after' else []
  for test in ([False,True] if cfg else [False]):
   print(f'{variant} / '+('checked-in unit test' if test else 'matrix'),flush=True)
   target=tmp/'native'
   s.run([rustc,'--edition','2024',str(path),'-o',str(target),*cfg,*(['--test'] if test else [])],check=True)
   s.run([str(target)],check=True)
