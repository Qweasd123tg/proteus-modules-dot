import argparse,tempfile,subprocess as sp
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('schema',type=Path);p.add_argument('--rustc',default='rustc');o=p.parse_args()
s=o.schema.read_text();raw=s[s.index('fn push_scope_part'):s.index('/// How a text control')].replace('pub fn','fn')
with tempfile.TemporaryDirectory() as d:
 d=Path(d);f=d/'probe.rs';f.write_text(Path(__file__).with_name('scopes.rs.in').read_text().replace('@@FUNS@@',raw))
 sp.run([o.rustc,'--edition=2024',str(f),'-O','-o',str(d/'probe')],check=True);sp.run([d/'probe'],check=True)
