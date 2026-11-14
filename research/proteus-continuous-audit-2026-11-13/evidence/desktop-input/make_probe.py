from pathlib import Path
import hashlib,json
out=Path(__file__).resolve().parent;root=out.parent
records=[]
def take(path,start_text,end_text):
 s=(root/path).read_text();a=s.index(start_text);b=s.index(end_text,a);v=s[a:b]
 records.append(dict(file=path,start_line=s[:a].count('\n')+1,end_line=s[:b].count('\n')+1,sha256=hashlib.sha256(v.encode()).hexdigest()))
 return v
fields='src/ui/extensions/declarative/fields.rs'
input_arm=take(fields,'            Node::Input {\n                id,\n                value,','            Node::Code {')
text_types=take(fields,'pub(super) enum Text {','/// Embedded prose keeps')
callback_setup=take('src/ui/extensions/declarative/fields/textarea.rs','pub(super) fn disclosure_id(', '/// Only the visible prefix')
# Real schema, only path attribute is adapted to locate its existing tests.
widget=(root/'src/declarative/widget.rs').read_text().replace('mod tests;', '#[path = "'+str(root/'src/declarative/widget/tests.rs')+'"]\nmod tests;')
(out/'probe/src/widget.rs').write_text(widget)
modules='\n'.join('#[path = "'+str(out/'probe/src/widget.rs' if m=='widget' else root/'src/declarative'/f'{m}.rs')+'"] pub mod '+m+';' for m in ['widget','tree','control','graph','lanes','list','svg'])
prelude=r'''#![allow(dead_code)]
pub use proteus_diff as diff;
use std::{cell::{Ref,RefCell},rc::Rc,collections::HashMap,marker::PhantomData,ops::{Deref,DerefMut}};
type SharedString=Rc<str>;
#[derive(Default)]struct App;
#[derive(Default)]struct Window;
struct Context<T>{app:App,phantom:PhantomData<T>}
impl<T> Default for Context<T>{fn default()->Self{Self{app:App,phantom:PhantomData}}}
impl<T> Deref for Context<T>{type Target=App;fn deref(&self)->&App{&self.app}}
impl<T> DerefMut for Context<T>{fn deref_mut(&mut self)->&mut App{&mut self.app}}
impl<T> Context<T>{fn new<U>(&mut self,f:impl FnOnce(&mut Context<U>)->U)->Entity<U>{Entity(Rc::new(RefCell::new(f(&mut Context::default()))))}}
struct Entity<T>(Rc<RefCell<T>>);
impl<T> Clone for Entity<T>{fn clone(&self)->Self{Self(self.0.clone())}}
impl<T> Entity<T>{
 fn read(&self,_:&App)->Ref<'_,T>{self.0.borrow()}
 fn update<R>(&self,_:&mut App,f:impl FnOnce(&mut T,&mut Context<T>)->R)->R{f(&mut self.0.borrow_mut(),&mut Context::default())}
}
#[derive(Clone,Copy)]struct FocusHandle;
#[derive(Debug)]enum InputEvent{Change,PressEnter{secondary:bool,shift:bool},Blur}
// Recording native-input shim: no OS/GPUI focus or geometry is simulated.
// set_value is silent, matching vendor/gpui-base/src/input/base/state.rs:1299-1328.
struct InputState{value:SharedString,placeholder:String,min_rows:usize,max_rows:usize,sets:usize}
type TextareaState=InputState;
impl InputState{
 fn new<T>(_:&mut Window,_:&mut Context<T>)->Self{Self{value:Rc::from(""),placeholder:String::new(),min_rows:1,max_rows:1,sets:0}}
 fn placeholder(mut self,s:String)->Self{self.placeholder=s;self}
 fn auto_grow(mut self,min:usize,max:usize)->Self{self.min_rows=min;self.max_rows=max;self}
 fn set_auto_grow<T>(&mut self,min:usize,max:usize,_:&mut Context<T>){self.min_rows=min;self.max_rows=max;}
 fn set_placeholder<T>(&mut self,s:String,_:&mut Window,_:&mut Context<T>){self.placeholder=s;}
 fn set_value<T>(&mut self,s:String,_:&mut Window,_:&mut Context<T>){self.value=Rc::from(s);self.sets+=1;}
 fn value(&self)->SharedString{self.value.clone()}
 fn text(&self)->SharedString{self.value.clone()}
 fn focus_handle(&self,_:&App)->FocusHandle{FocusHandle}
}
struct Subscription(Rc<dyn Fn(&mut DeclarativeView,&InputEvent,&mut Context<DeclarativeView>)>);
impl Context<DeclarativeView>{
 fn subscribe<U:'static>(&mut self,state:&Entity<U>,f:impl Fn(&mut DeclarativeView,Entity<U>,&InputEvent,&mut Context<DeclarativeView>)+'static)->Subscription{let state=state.clone();Subscription(Rc::new(move|view,event,cx|f(view,state.clone(),event,cx)))}
}
mod icons{pub fn lucide(_: &str)->Option<()>{None}}
'''
views=r'''
mod native{
 use super::*;
'''+text_types+r'''
 pub(super) mod textarea{
  use super::*;
'''+callback_setup+r'''
  pub fn preview(_: &str)->Option<String>{None}
 }
}
use native::{Text,TextInput};
use native::textarea;
#[derive(Default)]struct Fields{inputs:HashMap<String,TextInput>,disclosures:HashMap<String,bool>}
#[derive(Default)]struct DeclarativeView{fields:Fields,sent:Vec<(String,Option<serde_json::Value>)>,sequence:u64}
impl DeclarativeView{
 fn act(&mut self,action:String,value:Option<serde_json::Value>,_:&mut Context<Self>){self.sequence+=1;self.sent.push((action,value));}
 fn prepare_input(&mut self,node:&widget::Node,settings:bool,window:&mut Window,cx:&mut Context<Self>){use widget::Node;match node{
'''+input_arm+r'''
  _=>{}
 }}
}
'''
tests=r'''
#[cfg(test)]mod audit{
 use super::*;use serde_json::json;
 fn node(value:&str,lines:usize,search:bool)->widget::Node{
  let node:widget::Node=serde_json::from_value(json!({"type":"input","id":"message","value":value,"placeholder":"Commit","action":"message","submit":"commit","lines":lines,"search":search})).unwrap();node.validate().unwrap();node
 }
 fn prepare(view:&mut DeclarativeView,value:&str,lines:usize,search:bool){view.prepare_input(&node(value,lines,search),false,&mut Window,&mut Context::default());}
 fn state(view:&DeclarativeView)->Entity<InputState>{match &view.fields.inputs["message"].state{Text::Line(s)|Text::Area(s)=>s.clone()}}
 fn native_edit(view:&mut DeclarativeView,value:&str){state(view).0.borrow_mut().value=Rc::from(value);event(view,InputEvent::Change);}
 fn event(view:&mut DeclarativeView,event:InputEvent){let cb=view.fields.inputs["message"]._subscription.0.clone();cb(view,&event,&mut Context::default());}
 fn text(view:&DeclarativeView)->String{state(view).0.borrow().value.to_string()}
 fn reversion()->DeclarativeView{let mut v=DeclarativeView::default();prepare(&mut v,"",6,false);native_edit(&mut v,"x");native_edit(&mut v,"");v}
 #[test]fn observed_revert_to_acknowledged_value_emits_no_second_action(){
  for lines in [1,6]{let mut v=DeclarativeView::default();prepare(&mut v,"",lines,false);native_edit(&mut v,"x");native_edit(&mut v,"");assert_eq!(text(&v),"");assert_eq!(v.sent,[("message".into(),Some(json!("x")))]);assert_eq!(v.sequence,1);}
 }
 #[test]fn observed_old_reply_restores_deleted_text(){
  let mut v=reversion();assert_eq!(v.sequence,1);println!("NATIVE_ACTIONS={}",serde_json::to_string(&v.sent).unwrap());prepare(&mut v,"x",6,false);assert_eq!(text(&v),"x");
 }
 #[test]fn control_distinct_second_edit_sends_latest_value_and_advances_sequence(){
  let mut v=DeclarativeView::default();prepare(&mut v,"",1,false);native_edit(&mut v,"x");native_edit(&mut v,"y");assert_eq!(v.sent.len(),2);assert_eq!(v.sent.last().unwrap().1,Some(json!("y")));assert_eq!(v.sequence,2);
 }
 #[test]fn control_revert_after_first_echo_sends_clear(){let mut v=DeclarativeView::default();prepare(&mut v,"",6,false);native_edit(&mut v,"x");prepare(&mut v,"x",6,false);native_edit(&mut v,"");assert_eq!(v.sent.last().unwrap().1,Some(json!("")));assert_eq!(v.sequence,2);}
 #[test]fn control_programmatic_set_value_does_not_send_change(){let mut v=DeclarativeView::default();prepare(&mut v,"",6,false);prepare(&mut v,"server",6,false);assert_eq!(text(&v),"server");assert!(v.sent.is_empty());}
 #[test]fn observed_valid_multiline_to_search_retains_unrenderable_area(){let mut v=DeclarativeView::default();prepare(&mut v,"",6,false);prepare(&mut v,"",1,true);assert!(matches!(v.fields.inputs["message"].state,Text::Area(_)));}
 #[test]fn observed_multiline_height_update_is_ignored_until_text_changes_and_then_reverts_on_edit(){let mut v=DeclarativeView::default();prepare(&mut v,"",2,false);prepare(&mut v,"",6,false);assert_eq!(state(&v).0.borrow().min_rows,2);prepare(&mut v,"a",6,false);assert_eq!(state(&v).0.borrow().min_rows,6);native_edit(&mut v,"ab");assert_eq!(state(&v).0.borrow().min_rows,2);}
 #[test]fn control_initial_search_is_line_and_initial_height_applies(){let mut v=DeclarativeView::default();prepare(&mut v,"",1,true);assert!(matches!(v.fields.inputs["message"].state,Text::Line(_)));let mut v=DeclarativeView::default();prepare(&mut v,"",6,false);assert_eq!(state(&v).0.borrow().min_rows,6);}
 #[test]#[ignore="desired regression: current production loses clear"]fn required_clear_before_echo_is_sent(){let v=reversion();assert_eq!(v.sent.last().unwrap().1,Some(json!("")));assert_eq!(v.sequence,2);}
 #[test]#[ignore="desired regression: same id must adopt new line count"]fn required_multiline_to_search_uses_line_control(){let mut v=DeclarativeView::default();prepare(&mut v,"",6,false);prepare(&mut v,"",1,true);assert!(matches!(v.fields.inputs["message"].state,Text::Line(_)));}
 #[test]#[ignore="desired regression: latest lines must be retained"]fn required_height_stays_at_latest_after_edit(){let mut v=DeclarativeView::default();prepare(&mut v,"",2,false);prepare(&mut v,"a",6,false);native_edit(&mut v,"ab");assert_eq!(state(&v).0.borrow().min_rows,6);}
}
'''
# Only visibility adapts the copied type fields so tests outside their original
# module can observe state; production method bodies remain unchanged.
views=views.replace('    value: String,','    pub(super) value: String,').replace('    placeholder: String,','    pub(super) placeholder: String,').replace('    _subscription: Subscription,','    pub(super) _subscription: Subscription,')
views=views.replace('pub(super)', 'pub(crate)').replace('    fn set_placeholder(', '    pub(crate) fn set_placeholder(').replace('    fn set_value(', '    pub(crate) fn set_value(')
(out/'probe/src/lib.rs').write_text(prelude+modules+views+tests)
(out/'extractions.json').write_text(json.dumps(records,indent=2)+'\n')
