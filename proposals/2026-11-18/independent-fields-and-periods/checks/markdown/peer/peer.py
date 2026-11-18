#!/usr/bin/env python3
"""Check original and proposed md_cell in isolation against an independent line-ending oracle and GFM."""
import argparse,subprocess,tempfile,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--core',type=Path,required=True);p.add_argument('--patch',type=Path,required=True);p.add_argument('--markdown-rlib',type=Path,required=True);p.add_argument('--rustc',default='rustc');o=p.parse_args()
patch=o.patch.resolve();lib=o.markdown_rlib.resolve(strict=True);sha='8c6852cf920f8089d9e2721c7a590bafa0b2227cdede9dd78cb989af164ef80a'
assert hashlib.sha256(patch.read_bytes()).hexdigest()==sha
path='crates/proteus-core/src/core/topology_render/markdown.rs'
data=subprocess.check_output(['git','-C',o.core,'show','c2cbadee518788f306ffb2b5271036b2658ea8cc:'+path])
assert b'"| {} | {} | {} | {} |\\n"' in data and b'md_cell(&slot.responsibility)' in data
with tempfile.TemporaryDirectory() as td:
 root=Path(td);f=root/path;f.parent.mkdir(parents=True);f.write_bytes(data)
 for phase in ['before','after']:
  if phase=='after':subprocess.run(['git','apply',patch],cwd=root,check=True);subprocess.run(['git','apply','--reverse','--check',patch],cwd=root,check=True)
  s=f.read_text();i=s.index('fn md_cell');s=s[i:s.index('\n}',i)+2];rs=root/(phase+'.rs');rs.write_text((here/'peer.rs.in').read_text().replace('//CELL',s))
  exe=root/phase;subprocess.run([o.rustc,'--edition=2024','--extern','markdown='+str(lib),'-L','dependency='+str(lib.parent),rs,'-o',exe],check=True)
  q=subprocess.run([exe],capture_output=True,text=True);print(phase,q.stdout,sep='\n');assert q.returncode==(1 if phase=='before' else 0),q.stderr
