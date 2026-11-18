#!/usr/bin/env python3
import argparse,hashlib,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
def fn(s,start):
 i=s.index(start); j=s.index('{',i); d=1; k=j+1
 while d:
  d+=int(s[k]=='{')-int(s[k]=='}');k+=1
 return s[i:k]
src=(Path(__file__).parent/'matrix.rs.in').read_text()
paths=(a.before/'paths.rs').read_text()
src=src.replace('/*PATHS*/','\n'.join(fn(paths,'pub fn '+f+'(') for f in ['parent','parents','within']))
for token,tree,sha in [('A',a.before,'6fee4ead0e3ae0c37e53d107fd7efefcbbf1a6b08d90fec2db951bc41e646a1e'),('B',a.after,'49b934d220f97044dfda2db9b4516a8f6bc88b8530ceeb7500f21134160635e5')]:
 b=(tree/'tree.rs').read_bytes();assert hashlib.sha256(b).hexdigest()==sha;s=b.decode()
 x=fn(s,'pub fn expand_all(').replace('expand_all(',f'expand_{token.lower()}(',1)
 src=src.replace(f'/*{token}*/',x)
 if token=='A':src=src.replace('/*LISTING*/',fn(s,'fn listing('))
with tempfile.TemporaryDirectory() as td:
 f=Path(td)/'review.rs'; f.write_text(src);exe=f.with_suffix('')
 subprocess.run([a.rustc,'--edition=2024','-Awarnings',str(f),'-o',str(exe)],check=True); subprocess.run([str(exe)],check=True)
