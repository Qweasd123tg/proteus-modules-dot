"""Replay #194's original ordering/allocation workloads on the per-Workspace+iterator combination."""
import argparse,tempfile,subprocess as sp
from pathlib import Path
a=argparse.ArgumentParser();a.add_argument('dot',type=Path);a.add_argument('combined',type=Path);a.add_argument('--rustc',default='rustc');p=a.parse_args()
base='3bcb47225db2cfdd066a69d9c968026a6e9a597a:proposals/2026-11-17/fade-tree-tabs-and-tps/checks/tabs/'
def read(n):return sp.check_output(['git','-C',p.dot,'show',base+n],text=True)
head=read('head.inc');tail=read('tail.inc')
s=(p.combined/'src/ui/tabs/arrange.rs').read_text()
def block(start):
 i=s.index(start);j=s.index('{',i);d=1
 while d:j+=1;d+=int(s[j]=='{')-int(s[j]=='}')
 return s[i:j+1]
assert 'struct TabArrangement(Rc<RefCell<Arrange>>);' in s
head=head.replace('thread_local!{pub static STATE:RefCell<State>=RefCell::default();}', '''
type Arrange=State;
#[derive(Default)]pub struct TabArrangement(std::rc::Rc<RefCell<Arrange>>);
'''+block('impl TabArrangement {')+'''
thread_local!{pub static OWNER:TabArrangement=TabArrangement::default();}
pub struct TestState;
pub const STATE:TestState=TestState;
impl TestState{
 pub fn with_borrow<T>(&self,f:impl FnOnce(&State)->T)->T{OWNER.with(|o|f(&o.0.borrow()))}
 pub fn with_borrow_mut<T>(&self,f:impl FnOnce(&mut State)->T)->T{OWNER.with(|o|o.update(f))}
}
''')
# The previous harness models one window: hand the same fixture-owned handle to both callbacks.
wrap='''
pub(super) fn hover(p:&Pane,s:&str,pin:bool,b:Bounds<Pixels>,pt:Point<Pixels>,w:&mut Window){
 OWNER.with(|o|native_hover(o,p,s,pin,b,pt,w))
}
pub(super) fn drop_before(p:&Pane,s:&str)->Option<Option<String>>{
 OWNER.with(|o|native_drop(o,p,s))
}
'''
native=block('pub(super) fn hover(').replace('fn hover(','fn native_hover(',1)+'\n'+block('pub(super) fn drop_before(').replace('fn drop_before(','fn native_drop(',1)+'\n'+block("fn others<'a>")+'\n'+block('fn clamp(')
with tempfile.TemporaryDirectory() as td:
 d=Path(td);f=d/'prior.rs';f.write_text(head+native+'\n'+wrap+tail);sp.run([p.rustc,'--edition=2024','-O',f,'-o',d/'run'],check=True);sp.run([d/'run'],check=True)
