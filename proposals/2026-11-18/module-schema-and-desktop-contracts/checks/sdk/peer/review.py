"""Run actual rustdoc on the public lane-row example with a pure subset crate."""
from pathlib import Path
import argparse,tempfile,subprocess as s,re
p=argparse.ArgumentParser()
for x in ['before-ui','after-ui','deps','rustc','rustdoc']: p.add_argument('--'+x,required=True)
a=p.parse_args()
b=Path(a.before_ui).read_text();v=Path(a.after_ui).read_text()
assert [l for l in b.splitlines() if not l.startswith('///')]==[l for l in v.splitlines() if not l.startswith('///')]
def sub(a,b):return v[v.index(a):v.index(b,v.index(a))]
ui='use serde_json::{json,Value};\n'+sub('pub trait Node','pub fn text(')+sub('/// A list with a lane column','/// A disclosure animated')
lib='pub use serde_json::json; pub mod ui;'
with tempfile.TemporaryDirectory() as td:
 d=Path(td);(d/'ui.rs').write_text(ui);(d/'lib.rs').write_text(lib)
 dep=Path(a.deps);sj=next(dep.glob('libserde_json-*.rlib'))
 params=['--edition=2024','--crate-name','proteus_extension','--extern',f'serde_json={sj}','-L',f'dependency={dep}'];rl=d/'libproteus_extension.rlib'
 s.run([a.rustc,*params,'--crate-type','lib',d/'lib.rs','-o',rl],check=True)
 s.run([a.rustdoc,*params,'--extern',f'proteus_extension={rl}','--test',d/'lib.rs'],check=True)
print('all non-rustdoc lines match; generated tests use the published library name and real Rust doc parser')
