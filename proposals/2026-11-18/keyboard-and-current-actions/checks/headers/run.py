"""Run actual UI navigation/row synchronization methods on synthetic rows, without a window."""
from pathlib import Path
import argparse,subprocess as sp,tempfile
P=argparse.ArgumentParser();P.add_argument('before',type=Path);P.add_argument('after',type=Path);P.add_argument('--rustc',default='rustc');a=P.parse_args()
def fun(s,key):
 i=s.index(key);j=s.index('{',i);d=1
 while d:j+=1;d+=(s[j]=='{')-(s[j]=='}')
 return s[i:j+1]
with tempfile.TemporaryDirectory() as k:
 outs=[]
 for phase,tree in [('before',a.before),('after',a.after)]:
  d=Path(k);u=tree/'src/ui/extensions/declarative';s=(u/'tree.rs').read_text();row=(u/'tree_row.rs').read_text()
  assert 'tree.cursor = tree.step(tree.cursor, 1);' in s
  assert 'this.act_at(index, event, cx);' in row and 'if row.header()' in row
  start=row.index('index == Some(self.cursor)');end=row.index(',\n',start);ring=row[start:end].replace('crate::ui::kit::keyboard()', 'keyboard')
  methods='\n'.join(fun(s,n) for n in ['fn step(','fn key(','fn act(','pub fn set_rows('])
  text=Path(__file__).with_name('frame.rs.in').read_text().replace('/*METHODS*/',methods).replace('/*FOLDS*/',fun(s,'fn children(')+'\n'+fun(s,'fn folds('))
  text=text.replace('/*RING*/',ring).replace('/*HEADER*/',fun((tree/'src/declarative/tree.rs').read_text(),'pub fn header('))
  f=d/(phase+'.rs');f.write_text(text);exe=f.with_suffix('');sp.run([a.rustc,'--edition=2024','-Awarnings',f,'-o',exe],check=True)
  q=sp.check_output([exe,phase],text=True);outs.append(q[q.index('CONTROL'):]);print(phase+' '+q.strip())
 assert outs[0]==outs[1], 'ordinary and empty controls changed'
