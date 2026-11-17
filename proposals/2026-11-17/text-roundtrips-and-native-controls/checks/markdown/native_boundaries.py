"""Offline replay of 324 boundary checks. Supply Desktop and the upstream markdown-rs GFM table file."""
from pathlib import Path
import argparse, hashlib, os, subprocess, tempfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('desktop', type=Path)
p.add_argument('gfm_table', type=Path)
p.add_argument('--rustc', default='rustc')
a=p.parse_args()
md=a.gfm_table.read_bytes()
if hashlib.sha256(md).hexdigest()!='a5c5c0ca7cabb41cedc17fee4920b7adcd870d114d40c4294ea2ff067cf1d070':
    raise SystemExit('Expected src/construct/gfm_table.rs of markdown-rs 1.0.0, commit 1506572.')
node=(a.desktop/'vendor/gpui-base/src/text/node.rs').read_text()
def get(s,name):
    i=s.index('fn '+name+'(')
    return s[i:s.index('\n}\n',i)+2]
lexer='\n'.join(get(md.decode(),f) for f in ['head_row_data','head_row_escape','body_row_data','body_row_escape'])
serializer=(get(node,'protect_table_pipes')+'\n' if 'fn protect_table_pipes(' in node else '')+get(node,'table_selected_source')
frame=Path(__file__).with_name('boundary-frame.rs.in').read_text()
with tempfile.TemporaryDirectory() as t:
    d=Path(t); src=d/'main.rs'; src.write_text(frame.replace('//ACTUAL_LEXER',lexer).replace('//ACTUAL_SERIALIZER',serializer))
    subprocess.run([a.rustc,'--edition=2024',str(src),'-o',str(d/'check')],check=True)
    raise SystemExit(subprocess.run([str(d/'check')]).returncode)
