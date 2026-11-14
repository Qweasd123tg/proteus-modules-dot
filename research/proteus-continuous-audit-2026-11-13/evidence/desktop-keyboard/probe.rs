#![allow(dead_code)]
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

impl Tree {
fn act_at(&self, index: usize, event: &'static str, cx: &mut App) {
        if let Some(row) = self.rows.get(index) {
            (self.action)(row.id.clone(), event, cx);
        }
    }
fn act(&self, event: &'static str, cx: &mut App) {
        self.act_at(self.cursor, event, cx);
    }
fn step(&self, index: usize, toward: isize) -> usize {
        let item = |index: &usize| self.rows.get(*index).is_some_and(|row| !row.header());
        let index = index.min(self.rows.len().saturating_sub(1));
        let forward = (index..self.rows.len()).find(item);
        let backward = (0..=index).rev().find(item);
        let found = if toward >= 0 {
            forward.or(backward)
        } else {
            backward.or(forward)
        };
        found.unwrap_or(self.cursor)
    }
fn key(&mut self, event: &KeyDownEvent, cx: &mut Context<Self>) {
        let last = self.rows.len().saturating_sub(1);
        match event.keystroke.key.as_str() {
            "up" => self.cursor = self.step(self.cursor.saturating_sub(1), -1),
            "down" => self.cursor = self.step((self.cursor + 1).min(last), 1),
            "home" => self.cursor = self.step(0, 1),
            "end" => self.cursor = self.step(last, -1),
            "pageup" => self.cursor = self.step(self.cursor.saturating_sub(12), -1),
            "pagedown" => self.cursor = self.step((self.cursor + 12).min(last), 1),
            "space" => {
                self.act("select", cx);
                cx.stop_propagation();
                return;
            }
            "enter" => {
                self.act("open", cx);
                cx.stop_propagation();
                return;
            }
            "left" => {
                let Some(row) = self.rows.get(self.cursor) else {
                    return;
                };
                if row.expanded == Some(true) {
                    self.act("collapse", cx);
                    cx.stop_propagation();
                    return;
                }
                let depth = row.depth;
                match self.rows[..self.cursor]
                    .iter()
                    .rposition(|row| row.depth < depth && !row.header())
                {
                    Some(parent) => self.cursor = parent,
                    None => return,
                }
            }
            "right" => {
                let Some(row) = self.rows.get(self.cursor) else {
                    return;
                };
                let child = self
                    .rows
                    .get(self.cursor + 1)
                    .is_some_and(|next| next.depth > row.depth && !next.header());
                if row.expanded != Some(true) || !child {
                    self.act("expand", cx);
                    cx.stop_propagation();
                    return;
                }
                self.cursor += 1;
            }
            _ => return,
        }
        self.list.scroll_to_reveal_item(self.cursor);
        self.act("preview", cx);
        cx.notify();
        cx.stop_propagation();
    }
}

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
fn next_question(&mut self, rid: &str, window: &mut Window, cx: &mut Context<Self>) {
        let Some(request) = self.user_input_request(rid) else {
            return;
        };
        let page = self.user_input.page(request);
        let Some(question) = request.questions.get(page) else {
            return;
        };
        if !self.user_input.is_answered(rid, &question.id, cx) {
            return;
        }
        let count = request.questions.len();
        self.advance(rid, page, count, cx);
        if page + 1 >= count {
            self.focus(window, cx);
        }
    }
fn advance(&mut self, rid: &str, page: usize, count: usize, cx: &mut Context<Self>) {
        if page + 1 < count {
            self.user_input.set_page(rid, page + 1);
            cx.notify();
        } else {
            self.submit_user_input(rid, false, cx);
        }
    }
}

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
