#!/usr/bin/env python3
"""Source-fingerprinted geometry + actual desktop shortcut handler, isolated from GPUI."""
import argparse,hashlib,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("before",type=Path);p.add_argument("after",type=Path);p.add_argument("--rustc",default="rustc");a=p.parse_args()
def get(root,path,sha):
 b=(root/path).read_bytes();assert hashlib.sha256(b).hexdigest()==sha,(root,path);return b.decode()
def fn(s,start):
 i=s.index(start);j=s.index('{',i);d=1;k=j+1
 while d: d+=(s[k]=='{')-(s[k]=='}');k+=1
 return s[i:k]
base=(Path(__file__).parent/"geom.rs.in").read_text()
sz=get(a.before,'crates/tabs/src/size.rs','01c7279e53e230137d4b62c72b826d70f1fecb2d1720c516a9e541654f261327')
base=base.replace('/*EXTENTS*/',fn(sz,'fn extents(')).replace('/*WEIGHT*/',fn(sz,'fn weight('))
with tempfile.TemporaryDirectory() as tmp:
 for tag,r,g,o,u in [
 ('before',a.before,'e918b70f960a5ab2b5a09cbe2e572150e9e94fb786bda56f9742e015c36261e9','4c6c9e5b6e9cb579b713ad097d8e645213a6fa45b40c4dba4ae473fd4ab36faf','8386f2aeea0fc4c19fe5f0bc0559e0defbc8d628189757286de8ae0caf336f69'),
 ('after',a.after,'7d73393a09a86abfd7ea868592fc9c596facd3f4df49dbaaab53889bf08a6587','088edc44f0271d976e6546836361b4cd365e31d0c671ccb5c0ccb4636183245a','ad2cceee18f8024f2e152ba3b1328c5587b9d69cd0011e9fe9ff976abe1ece90')]:
  g=get(r,'crates/tabs/src/geometry.rs',g);o=get(r,'crates/tabs/src/ops.rs',o);u=get(r,'src/ui/tabs/mod.rs',u)
  code=base.replace('/*PLACE*/',fn(g,'fn place(')).replace('/*REFERENCE*/',next(l for l in g.splitlines() if l.startswith('const REFERENCE:'))).replace('/*EPSILON*/',next(l for l in g.splitlines() if l.startswith('const EPSILON:')))
  methods=[('rects_in',g),('rects_spaced',g),('rects',g),('rect',g),('neighbor',g),('focus_neighbor',o)]
  if tag=='after':methods.extend([('neighbor_in',g),('focus_neighbor_in',o)])
  code=code.replace('/*METHODS*/','\n'.join(fn(s,'fn '+n+'(') for n,s in methods))
  code=code.replace('/*ACTION*/',fn(u,'fn focus_neighbor('));f=Path(tmp)/(tag+'.rs');f.write_text(code)
  exe=f.with_suffix('');subprocess.run([a.rustc,'--edition=2024','-Awarnings',str(f),'-o',str(exe)],check=True);subprocess.run([str(exe),tag],check=True)
