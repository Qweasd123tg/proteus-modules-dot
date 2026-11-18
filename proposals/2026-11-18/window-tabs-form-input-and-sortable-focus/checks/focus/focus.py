"""Compile the actual prepaint key membership test and height construction with instrumented ids."""
from pathlib import Path
import subprocess as sp,tempfile,argparse
P=argparse.ArgumentParser();P.add_argument('before',type=Path);P.add_argument('after',type=Path);P.add_argument('--rustc',default='rustc');a=P.parse_args()
with tempfile.TemporaryDirectory() as t:
 for phase,z in [('before',a.before),('after',a.after)]:
  s=(z/'src/ui/reorder.rs').read_text();base=s.index('impl Element for Arrange {')
  body=s[s.index('            state.exclusions.clear();',base)+len('            state.exclusions.clear();'):s.index('            let order =',base)].strip()
  assert body.count('state.focus.retain')==1
  # Bracket only the retention statement; constructing heights is common to both versions.
  q=body.index('state.focus.retain');body=body[:q]+'reset_counters();\n'+body[q:];q=body.index(';',body.index('state.focus.retain'));body=body[:q+1]+'\n            let cost=counts();'+body[q+1:]
  assert 'let ids: Vec<_> = self.rows.iter().map(|row| row.id.clone()).collect();' in s
  assert 'let children = self\n            .rows\n            .into_iter()\n            .enumerate()\n            .map(' in s and '.child(Arrange {\n                ids,\n                children,' in s
  assert 'let children: Vec<_> = self\n            .children\n            .iter_mut()\n            .map(|child| child.request_layout(window, cx))' in s
  assert '(window.request_layout(style, children.clone(), cx), children)' in s
  assert '.zip(layouts.iter().map(|id| window.layout_bounds(*id)))' in s
  code=Path(__file__).with_name('frame.rs.in').read_text().replace('/*PREPAINT*/',body)
  f=Path(t)/(phase+'.rs');f.write_text(code);e=f.with_suffix('');sp.run([a.rustc,'--edition=2024','-O',f,'-o',e],check=True);sp.run([e,phase],check=True)
