"""Run the exact proposed regression against the original and the proposed cell writer."""
from pathlib import Path
import argparse,subprocess as sp,tempfile
a=argparse.ArgumentParser();a.add_argument('before',type=Path);a.add_argument('after',type=Path);a.add_argument('--rustc',default='rustc');p=a.parse_args()
n='crates/proteus-core/src/core/topology_render/markdown.rs';s=(p.after/n).read_text();tests=s[s.rindex('#[cfg(test)]'):]
with tempfile.TemporaryDirectory() as td:
 for v in ['before','after']:
  s=(getattr(p,v)/n).read_text();i=s.index('fn md_cell(');code=s[i:s.index('\n}\n',i)+2];f=Path(td)/(v+'.rs');f.write_text(code+'\n'+tests);e=f.with_suffix('')
  sp.run([p.rustc,'--edition=2024','--test',f,'-o',e],check=True);r=sp.run([e],capture_output=True,text=True)
  if v=='before':assert r.returncode!=0 and 'one_cell_flattens_each_logical_line_break_once' in r.stdout
  else:assert r.returncode==0 and '1 passed' in r.stdout
  print(v+': exact Core cell-writer regression '+('FAIL (expected)' if r.returncode else 'PASS'))
