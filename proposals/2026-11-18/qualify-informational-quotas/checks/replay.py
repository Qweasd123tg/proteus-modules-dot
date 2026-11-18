"""Native projections only. No live account, host, provider, OS clock, network or GUI."""
from pathlib import Path
import argparse,re,subprocess as sp,tempfile
p=argparse.ArgumentParser(description=__doc__)
for n in ('base','candidate','extensions','core','deps'):p.add_argument(n,type=Path)
p.add_argument('--rustc',default='rustc');a=p.parse_args()
e=a.extensions;d=a.deps.resolve()
def block(s,key):
 start=s.index(key);j=s.index('{',start)+1;n=1
 while n:n+=int(s[j]=='{')-int(s[j]=='}');j+=1
 return s[start:j]
def prod(s):return '\n'.join(v for v in s.split('#[cfg(test)]',1)[0].splitlines() if not v.startswith('//!'))
s=(e/'sdk/src/ui.rs').read_text();v=prod((e/'sdk/src/value.rs').read_text())
ui='\n'.join(block(s,k) for k in ['pub trait Node {','impl Node for Value {','pub fn text(','pub fn note(','pub fn card(','pub fn progress(','pub fn table(','pub fn kv('])
dto_path=a.core/'crates/proteus-contracts/src/contracts/model_quota.rs'
with dto_path.open() as stream:
 dto=''
 for line in stream:
  if line.startswith('impl ModelQuotaSnapshot'):break
  if not line.startswith('//!'):dto+=line
z=Path(__file__).with_name('fixture.rs.in').read_text().replace('/*DTO*/',dto).replace('/*VALUE*/',v).replace('/*UI*/',ui)
test=None
for which,r in [('old',a.base),('new',a.candidate)]:
 sub=r/'packages/quota/src';desc=(sub/'describe.rs').read_text();view=(sub/'view.rs').read_text()
 code='pub mod describe {'+prod(desc)+'}\npub mod view {'+prod(view).replace('crate::describe','crate::'+which+'::describe')+'}'
 z=z.replace('/*'+which+'*/',code)
 if which=='new':test=block(view,'fn informational_bucket_explains_scope_without_hiding_reported_status(')
with tempfile.TemporaryDirectory() as tmp:
 t=Path(tmp);rs=t/'f.rs';rs.write_text(z);cmd=[a.rustc,'--edition=2024','-Awarnings','-O','-L','dependency='+str(d)]
 for k in ('serde','serde_json'):rlib,=d.glob('lib'+k+'-*.rlib');cmd+=['--extern',k+'='+str(rlib)]
 sp.run([*cmd,rs,'-o',t/'run'],check=True);sp.run([t/'run'],check=True)
 for side,ok in [('old',False),('new',True)]:
  # Same in-patch test against the old display, supplying only the expected marker as a test constant.
  # No such marker is inserted into the old production presenter.
  note='const INFORMATIONAL_SCOPE:&str=crate::SCOPE;' if side=='old' else 'use crate::new::describe::INFORMATIONAL_SCOPE;'
  u=test.replace('use crate::describe::{INFORMATIONAL_SCOPE, describe};',note+' use crate::'+side+'::describe::describe;')
  assert note in u;rs.write_text(z+'\n#[cfg(test)] mod ported {use super::*;use '+side+'::view::render; #[test] '+u+'}')
  sp.run([*cmd,'--test',rs,'-o',t/'unit'],check=True);q=sp.run([t/'unit'],capture_output=True,text=True)
  assert (q.returncode==0)==ok,q.stdout
  if not ok:assert 'assertion `left == right` failed' in q.stdout
  print(side,'in-tree regression',('green' if ok else 'behavioral red (missing qualifier)'))
