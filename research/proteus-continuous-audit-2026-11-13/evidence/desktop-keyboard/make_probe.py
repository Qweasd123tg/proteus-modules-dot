from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[1]
out=Path(__file__).resolve().parent
records=[]
def extract(path,name):
    text=(root/path).read_text(); start=text.index('fn '+name+'('); start=text.rfind('\n',0,start)+1
    brace=text.index('{',start); depth=1; i=brace+1
    while depth:
        depth+=(text[i]=='{')-(text[i]=='}');i+=1
    code=text[start:i].strip()
    records.append(dict(file=path,function=name,start_line=text[:start].count('\n')+1,end_line=text[:i].count('\n')+1,sha256=hashlib.sha256(code.encode()).hexdigest()))
    return code.replace('pub(super) ', '').replace('pub(in crate::ui) ', '')
tree='\n'.join(extract('src/ui/extensions/declarative/tree.rs',n) for n in ['act_at','act','step','key'])
question='\n'.join(extract('src/ui/chat/question_card.rs',n) for n in ['next_question','advance'])
prelude=r'''#![allow(dead_code)]
use std::{collections::HashMap,marker::PhantomData,ops::{Deref,DerefMut},rc::Rc};
#[derive(Default)]struct App { events:Vec<(String,&'static str)>,notifications:usize,stopped:bool }
struct Context<T>{app:App,_type:PhantomData<T>}
impl<T> Default for Context<T>{fn default()->Self{Self{app:App::default(),_type:PhantomData}}}
impl<T> Context<T>{fn notify(&mut self){self.app.notifications+=1;}fn stop_propagation(&mut self){self.app.stopped=true;}}
impl<T> Deref for Context<T>{type Target=App;fn deref(&self)->&App{&self.app}}
impl<T> DerefMut for Context<T>{fn deref_mut(&mut self)->&mut App{&mut self.app}}
#[derive(Clone)]struct Row{id:String,expanded:Option<bool>,depth:usize,is_header:bool,checked:Option<bool>}
impl Row{fn header(&self)->bool{self.is_header}}
#[derive(Default)]struct List{revealed:Vec<usize>}
impl List{fn scroll_to_reveal_item(&mut self,i:usize){self.revealed.push(i)}}
struct Tree{rows:Vec<Row>,cursor:usize,list:List,action:Rc<dyn Fn(String,&'static str,&mut App)>}
struct Keystroke{key:String}
struct KeyDownEvent{keystroke:Keystroke}
impl KeyDownEvent{fn new(key:&str)->Self{Self{keystroke:Keystroke{key:key.into()}}}}
'''
question_stubs=r'''
struct Window { focused:String }
struct Question { id:String }
struct Request { questions:Vec<Question> }
#[derive(Default)]struct Drafts { pages:HashMap<String,usize>,answered:HashMap<String,bool> }
impl Drafts {
 fn page(&self,_:&Request)->usize{*self.pages.get("r").unwrap_or(&0)}
 fn is_answered(&self,_:&str,q:&str,_:&App)->bool{self.answered.get(q).copied().unwrap_or(false)}
 fn set_page(&mut self,r:&str,p:usize){self.pages.insert(r.into(),p);}
}
struct Chat { request:Request,user_input:Drafts,submitted:usize }
impl Chat {
 fn user_input_request(&self,_:&str)->Option<&Request>{Some(&self.request)}
 fn focus(&self,w:&mut Window,_:&mut Context<Self>){w.focused="composer".into()}
 fn submit_user_input(&mut self,_:&str,_:bool,_:&mut Context<Self>){self.submitted+=1;}
'''
tests=r'''
#[cfg(test)]mod audit{
 use super::*;
 fn row(id:&str,checked:Option<bool>)->Row{Row{id:id.into(),checked,expanded:None,depth:1,is_header:false}}
 fn tree(rows:Vec<Row>)->Tree{Tree{rows,cursor:0,list:List::default(),action:Rc::new(|id,event,cx|cx.events.push((id,event)))}}
 fn chat()->Chat{Chat{request:Request{questions:vec![Question{id:"q1".into()},Question{id:"q2".into()}]},user_input:Drafts{pages:HashMap::new(),answered:HashMap::from([("q1".into(),true),("q2".into(),true)])},submitted:0}}
 #[test]fn observed_space_on_checked_unchecked_and_plain_rows_emits_select_not_check(){
  for checked in [Some(false),Some(true),None]{let mut t=tree(vec![row("file:b.py",checked)]);let mut cx=Context::default();t.key(&KeyDownEvent::new("space"),&mut cx);assert_eq!(cx.events,[("file:b.py".into(),"select")]);assert!(cx.stopped);}
 }
 #[test]fn observed_no_supported_tree_key_produces_check(){
  for key in ["up","down","home","end","pageup","pagedown","space","enter","left","right","tab","f10","contextmenu"]{let mut t=tree(vec![row("file:b.py",Some(false))]);let mut cx=Context::default();t.key(&KeyDownEvent::new(key),&mut cx);assert!(!cx.events.iter().any(|(_,event)|*event=="check"),"{key}");}
 }
 #[test]fn control_pointer_checkbox_callback_can_emit_check(){
  let t=tree(vec![row("file:b.py",Some(false))]);let mut cx=Context::<Tree>::default();t.act_at(0,"check",&mut cx);assert_eq!(cx.events,[("file:b.py".into(),"check")]);
 }
 #[test]fn observed_enter_next_question_keeps_old_input_focus(){
  let mut c=chat();let mut w=Window{focused:"input:r:q1".into()};c.next_question("r",&mut w,&mut Context::default());assert_eq!(c.user_input.page(&c.request),1);assert_eq!(w.focused,"input:r:q1");assert_eq!(c.submitted,0);
 }
 #[test]fn control_last_question_explicitly_restores_composer_focus(){
  let mut c=chat();c.user_input.set_page("r",1);let mut w=Window{focused:"input:r:q2".into()};c.next_question("r",&mut w,&mut Context::default());assert_eq!(c.submitted,1);assert_eq!(w.focused,"composer");
 }
 #[test]fn control_unanswered_question_does_not_move_page(){
  let mut c=chat();c.user_input.answered.clear();let mut w=Window{focused:"input:r:q1".into()};c.next_question("r",&mut w,&mut Context::default());assert_eq!(c.user_input.page(&c.request),0);assert_eq!(w.focused,"input:r:q1");
 }
 #[test]#[ignore="desired behavior; known red on inspected production methods"]
 fn required_space_on_checkbox_emits_check(){let mut t=tree(vec![row("file:b.py",Some(false))]);let mut cx=Context::default();t.key(&KeyDownEvent::new("space"),&mut cx);assert_eq!(cx.events,[("file:b.py".into(),"check")]);}
 #[test]#[ignore="desired behavior; known red on inspected production methods"]
 fn required_next_question_releases_unmounted_input_focus(){let mut c=chat();let mut w=Window{focused:"input:r:q1".into()};c.next_question("r",&mut w,&mut Context::default());assert_ne!(w.focused,"input:r:q1");}
}
'''
(out/'probe.rs').write_text(prelude+'\nimpl Tree {\n'+tree+'\n}\n'+question_stubs+question+'\n}\n'+tests)
(out/'extractions.json').write_text(json.dumps(records,indent=2)+'\n')
# No native screen/OS key dispatch: production key reducer and question methods,
# standard-library recording stubs only. The extension consumer is tested separately.
