"""Extract only the pinned pure table-cell serializer and observe bytes & actual GFM AST.

python check.py CORE --markdown-rlib PATH_TO_LIBMARKDOWN_RLIB [--rustc PATH]
The parser library should be markdown-rs 1.0.0, with deps next to its rlib.
No Core build, registry/network or project code beyond md_cell is invoked.
"""
import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--markdown-rlib',type=Path,required=True);p.add_argument('--rustc',default='rustc')
a=p.parse_args();f=a.core/'crates/proteus-core/src/core/topology_render/markdown.rs';s=f.read_text()
i=s.index('fn md_cell(');j=s.index('\n}\n',i)+2;func=s[i:j]
row='| {} | {} | {} | {} | {} | {} |\\n'
assert row in s and 'md_cell(&tool.description)' in s
spec=Path(__file__).with_name('cell.rs.in').read_text().replace('/*CELL*/',func)
with tempfile.TemporaryDirectory() as tmp:
 d=Path(tmp);rs=d/'test.rs';rs.write_text(spec);rl=a.markdown_rlib.resolve()
 subprocess.run([a.rustc,'--edition=2024',str(rs),'--extern','markdown='+str(rl),'-L','dependency='+str(rl.parent),'-o',str(d/'native')],check=True)
 subprocess.run([str(d/'native')],check=True)
