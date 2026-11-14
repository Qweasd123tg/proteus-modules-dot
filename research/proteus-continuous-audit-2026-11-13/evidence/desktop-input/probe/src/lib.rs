#![allow(dead_code)]
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
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/audit-ui-composition/probe/src/widget.rs"] pub mod widget;
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/declarative/tree.rs"] pub mod tree;
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/declarative/control.rs"] pub mod control;
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/declarative/graph.rs"] pub mod graph;
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/declarative/lanes.rs"] pub mod lanes;
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/declarative/list.rs"] pub mod list;
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/declarative/svg.rs"] pub mod svg;
mod native{
 use super::*;
pub(crate) enum Text {
    Line(Entity<InputState>),
    Area(Entity<TextareaState>),
}

impl Text {
    pub fn value(&self, cx: &App) -> SharedString {
        match self {
            Text::Line(state) => state.read(cx).value(),
            Text::Area(state) => state.read(cx).value(),
        }
    }

    pub fn focus_handle(&self, cx: &App) -> FocusHandle {
        match self {
            Text::Line(state) => state.read(cx).focus_handle(cx),
            Text::Area(state) => state.read(cx).focus_handle(cx),
        }
    }

    pub(crate) fn set_placeholder(&self, placeholder: String, window: &mut Window, cx: &mut App) {
        match self {
            Text::Line(state) => state.update(cx, |input, cx| {
                input.set_placeholder(placeholder, window, cx)
            }),
            Text::Area(state) => state.update(cx, |input, cx| {
                input.set_placeholder(placeholder, window, cx)
            }),
        }
    }

    pub(crate) fn set_value(&self, value: String, window: &mut Window, cx: &mut App) {
        match self {
            Text::Line(state) => state.update(cx, |input, cx| input.set_value(value, window, cx)),
            Text::Area(state) => state.update(cx, |input, cx| input.set_value(value, window, cx)),
        }
    }
}

pub(crate) struct TextInput {
    pub state: Text,
    pub settings: bool,
    pub grow: bool,
    pub(crate) value: String,
    pub(crate) placeholder: String,
    pub(crate) _subscription: Subscription,
}


 pub(crate) mod textarea{
  use super::*;
pub(crate) fn disclosure_id(id: &str) -> String {
    format!("input-preview:{id}")
}

/// This limits measured display rows, rather than allocating a fixed height.
pub(crate) fn max_rows(value: &str, min_rows: usize, grow: bool) -> usize {
    if grow {
        value.chars().count().saturating_add(1).max(min_rows)
    } else {
        min_rows
    }
}

pub(crate) fn resize(state: &Entity<TextareaState>, min_rows: usize, grow: bool, cx: &mut App) {
    let max = if grow {
        state
            .read(cx)
            .text()
            .chars()
            .count()
            .saturating_add(1)
            .max(min_rows)
    } else {
        min_rows
    };
    state.update(cx, |state, cx| state.set_auto_grow(min_rows, max, cx));
}


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
            Node::Input {
                id,
                value,
                placeholder,
                action,
                lines,
                submit,
                ..
            } => {
                let grow = settings && *lines > 1;
                if let Some(input) = self.fields.inputs.get_mut(id) {
                    let layout_changed = input.grow != grow || input.value != *value;
                    input.settings = settings;
                    input.grow = grow;
                    if input.placeholder != *placeholder {
                        input.placeholder = placeholder.clone();
                        input.state.set_placeholder(placeholder.clone(), window, cx);
                    }
                    if input.value != *value {
                        input.value = value.clone();
                        if input.state.value(cx).as_ref() != value {
                            input.state.set_value(value.clone(), window, cx);
                        }
                    }
                    if layout_changed && let Text::Area(state) = &input.state {
                        textarea::resize(state, *lines, grow, cx);
                    }
                } else {
                    let multi = *lines > 1;
                    let (action, submit, identity) = (action.clone(), submit.clone(), id.clone());
                    let handle =
                        move |this: &mut DeclarativeView,
                              text: SharedString,
                              event: &InputEvent,
                              cx: &mut Context<DeclarativeView>| {
                            match event {
                                InputEvent::Change
                                    if this
                                        .fields
                                        .inputs
                                        .get(&identity)
                                        .is_some_and(|input| input.value != text.as_ref()) =>
                                {
                                    this.act(
                                        action.clone(),
                                        Some(serde_json::json!(text.to_string())),
                                        cx,
                                    )
                                }
                                InputEvent::PressEnter { secondary, .. } if *secondary == multi => {
                                    if let Some(submit) = &submit {
                                        this.act(
                                            submit.clone(),
                                            Some(serde_json::json!(text.to_string())),
                                            cx,
                                        )
                                    }
                                }
                                _ => {}
                            }
                        };
                    let (state, subscription) = if multi {
                        let state = cx.new(|cx| {
                            let mut input = TextareaState::new(window, cx)
                                .auto_grow(*lines, textarea::max_rows(value, *lines, grow))
                                .placeholder(placeholder.clone());
                            input.set_value(value.clone(), window, cx);
                            input
                        });
                        let (input_id, min_rows) = (id.clone(), *lines);
                        let subscription = cx.subscribe(&state, move |this, state, event, cx| {
                            if matches!(event, InputEvent::Change) {
                                let grow = this
                                    .fields
                                    .inputs
                                    .get(&input_id)
                                    .is_some_and(|input| input.grow);
                                textarea::resize(&state, min_rows, grow, cx);
                                if grow && textarea::preview(&state.read(cx).value()).is_some() {
                                    this.fields
                                        .disclosures
                                        .insert(textarea::disclosure_id(&input_id), true);
                                }
                            }
                            let text = state.read(cx).value();
                            handle(this, text, event, cx)
                        });
                        (Text::Area(state), subscription)
                    } else {
                        let state = cx.new(|cx| {
                            let mut input =
                                InputState::new(window, cx).placeholder(placeholder.clone());
                            input.set_value(value.clone(), window, cx);
                            input
                        });
                        let subscription = cx.subscribe(&state, move |this, state, event, cx| {
                            let text = state.read(cx).value();
                            handle(this, text, event, cx)
                        });
                        (Text::Line(state), subscription)
                    };
                    self.fields.inputs.insert(
                        id.clone(),
                        TextInput {
                            state,
                            settings,
                            grow,
                            value: value.clone(),
                            placeholder: placeholder.clone(),
                            _subscription: subscription,
                        },
                    );
                }
            }

  _=>{}
 }}
}

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
