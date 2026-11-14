from pathlib import Path
import hashlib,json
out=Path(__file__).resolve().parent
root=out.parent
text=(root/'src/ui/extensions/declarative/view.rs').read_text()
start=text.index('    fn prepare_steps(');end=text.index('\n}\n\nimpl DeclarativeView {',start)
method=text[start:end].replace('fn prepare_steps','pub fn prepare_steps',1)
(out/'steps-extraction.json').write_text(json.dumps({'file':'src/ui/extensions/declarative/view.rs','start_line':text[:start].count('\n')+1,'end_line':text[:end].count('\n')+1,'sha256':hashlib.sha256(text[start:end].encode()).hexdigest()},indent=2)+'\n')
widget_source=(root/'src/declarative/widget.rs').read_text()
widget_copy=out/'steps-probe/src/widget.rs'
widget_copy.write_text(widget_source.replace('mod tests;', '#[path = "'+str(root/'src/declarative/widget/tests.rs')+'"]\nmod tests;'))
modules='\n'.join('#[path = "'+str(widget_copy if m=='widget' else root/'src/declarative'/f'{m}.rs')+'"] pub mod '+m+';' for m in ['widget','tree','control','graph','lanes','list','svg'])
pre=r'''#![allow(dead_code)]
pub use proteus_diff as diff;
use std::{cell::RefCell,rc::{Rc,Weak}};
struct App;
struct Entity<T>(Rc<RefCell<T>>);
impl<T> Clone for Entity<T>{fn clone(&self)->Self{Self(self.0.clone())}}
struct WeakEntity<T>(Weak<RefCell<T>>);
impl<T> Clone for WeakEntity<T>{fn clone(&self)->Self{Self(self.0.clone())}}
struct Context<T>{owner:WeakEntity<T>}
impl<T> Context<T>{
 fn notify(&self){}
 fn weak_entity(&self)->WeakEntity<T>{self.owner.clone()}
 fn new<U>(&mut self,f:impl FnOnce(&mut Context<U>)->U)->Entity<U>{Entity::new(f)}
}
impl<T> Entity<T>{
 fn new(f:impl FnOnce(&mut Context<T>)->T)->Self{Self(Rc::new_cyclic(|weak|RefCell::new(f(&mut Context{owner:WeakEntity(weak.clone())}))))}
 fn update<C,R>(&self,_:&mut C,f:impl FnOnce(&mut T,&mut Context<T>)->R)->R{f(&mut self.0.borrow_mut(),&mut Context{owner:WeakEntity(Rc::downgrade(&self.0))})}
}
impl<T> WeakEntity<T>{fn update<C,R>(&self,cx:&mut C,f:impl FnOnce(&mut T,&mut Context<T>)->R)->Result<R,()>{self.0.upgrade().map(|e|Entity(e).update(cx,f)).ok_or(())}}
// Production schema uses icon validation for unrelated node kinds. No icons
// occur in these fixtures; the GPUI-only enum is not needed to validate Steps.
mod icons { pub fn lucide(_: &str)->Option<()> {None} }
'''
views=r'''
mod steps {
 use super::*;
 pub struct Stepper{pub options:Vec<String>,pub selected:usize,pub changed:Rc<dyn Fn(usize,&mut App)>}
 impl Stepper{pub fn new(options:Vec<String>,selected:usize,changed:impl Fn(usize,&mut App)+'static)->Self{Self{options,selected,changed:Rc::new(changed)}}}
}
mod views {
 use super::*;
 use widget::Node;
 #[derive(Default)]pub struct DeclarativeView{pub steps:std::collections::HashMap<String,Entity<steps::Stepper>>,pub sent:Vec<(String,Option<serde_json::Value>)>}
 impl DeclarativeView{
 fn act(&mut self,action:String,value:Option<serde_json::Value>,_:&mut Context<Self>){self.sent.push((action,value))}
'''
tests=r'''
#[cfg(test)]mod audit {
 use super::*;
 use serde_json::{json,Value};
 fn step(action:&str,selected:usize)->Value{json!({"type":"steps","id":"effort","options":["low","high"],"selected":selected,"action":action})}
 fn setting(control:Value)->Value{json!({"type":"setting_row","id":"reasoning","label":"Effort","control":control})}
 fn node(value:Value)->widget::Node{let n:widget::Node=serde_json::from_value(value).unwrap();n.validate().unwrap();n}
 fn view()->Entity<views::DeclarativeView>{Entity::new(|_|Default::default())}
 #[test]fn control_top_level_steps_creates_control(){
  let v=view();v.update(&mut App,|v,cx|v.prepare_steps(&node(step("effort",0)),cx));assert_eq!(v.0.borrow().steps.len(),1);
 }
 #[test]fn observed_valid_setting_row_steps_is_missing_from_prepared_controls(){
  let root=node(setting(step("effort",0)));let mut found=0;root.visit(&mut |n|if matches!(n,widget::Node::Steps{..}){found+=1});assert_eq!(found,1);
  let v=view();v.update(&mut App,|v,cx|v.prepare_steps(&root,cx));assert!(v.0.borrow().steps.get("effort").is_none());
 }
 #[test]fn observed_reparented_steps_keeps_stale_options_and_selection(){
  let v=view();v.update(&mut App,|v,cx|v.prepare_steps(&node(step("effort",0)),cx));
  let next=node(setting(json!({"type":"steps","id":"effort","options":["new0","new1","new2"],"selected":2,"action":"effort"})));
  v.update(&mut App,|v,cx|v.prepare_steps(&next,cx));let steps=v.0.borrow().steps["effort"].clone();
  assert_eq!(steps.0.borrow().selected,0);assert_eq!(steps.0.borrow().options,["low","high"]);
 }
 #[test]fn observed_same_id_action_change_keeps_old_action_callback(){
  let v=view();v.update(&mut App,|v,cx|v.prepare_steps(&node(step("old_action",0)),cx));
  v.update(&mut App,|v,cx|v.prepare_steps(&node(step("new_action",1)),cx));
  let s=v.0.borrow().steps["effort"].clone();assert_eq!(s.0.borrow().selected,1);
  let callback=s.0.borrow().changed.clone();callback(0,&mut App);assert_eq!(v.0.borrow().sent,[("old_action".into(),Some(json!(0)))]);
 }
 #[test]#[ignore="desired behavior; known red on exact production prepare_steps"]
 fn required_steps_under_setting_row_is_prepared(){let v=view();v.update(&mut App,|v,cx|v.prepare_steps(&node(setting(step("effort",0))),cx));assert!(v.0.borrow().steps.contains_key("effort"));}
 #[test]#[ignore="desired behavior; known red on exact production prepare_steps"]
 fn required_same_id_steps_uses_latest_action(){let v=view();v.update(&mut App,|v,cx|v.prepare_steps(&node(step("old_action",0)),cx));v.update(&mut App,|v,cx|v.prepare_steps(&node(step("new_action",0)),cx));let s=v.0.borrow().steps["effort"].clone();let callback=s.0.borrow().changed.clone();callback(0,&mut App);assert_eq!(v.0.borrow().sent,[("new_action".into(),Some(json!(0)))]);}
}
'''
(out/'steps-probe/src/lib.rs').write_text(pre+modules+views+method+'\n}}\n'+tests)
