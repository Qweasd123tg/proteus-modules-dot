"""Peer check using a Core checkout and its before/after display-only patch. No Cargo, CLI or GUI.
python3 run.py <before-checkout> <after-checkout> <rustc> <compiled-serde-deps-dir>
"""
from pathlib import Path
import subprocess as sp,sys,tempfile,shutil
b,a,r,d=map(Path,sys.argv[1:]); template=Path(__file__).with_name('main.rs.in').read_text()
def q(x):return '"' + str(x).replace('\\','\\\\').replace('"','\\"') + '"'
with tempfile.TemporaryDirectory() as temp:
 t=Path(temp); R=Path('crates/proteus-core/src/core/topology_render'); dto=Path('crates/proteus-contracts/src/app_protocol/topology.rs')
 src = template.replace('DTO_FILE',q((b/dto).resolve()))
 for f in ['helpers','map','table','markdown']:
  src=src.replace(f.upper()+'_BEFORE',q((b/R/(f+'.rs')).resolve())).replace(f.upper()+'_AFTER',q(((a if f in ['table','markdown'] else b)/R/(f+'.rs')).resolve()))
 (t/'main.rs').write_text(src)
 cmd=[str(r),'--edition=2024','-Awarnings','-O',t/'main.rs','-L','dependency='+str(d.resolve())]
 for lib in ('serde','serde_json'):cmd.extend(['--extern',lib+'='+str(next(d.glob(f'lib{lib}-*.rlib')).resolve())])
 sp.run([*cmd,'-o',t/'peer'],check=True);sp.run([t/'peer'],check=True)
