
#![allow(dead_code)]
use std::{collections::HashMap,rc::Rc,cell::RefCell,marker::PhantomData};
mod ui {pub mod workspace {pub struct Workspace;}}
struct WeakEntity<T>(PhantomData<T>);
impl<T> Clone for WeakEntity<T>{fn clone(&self)->Self{Self(PhantomData)}}
struct Context<T>(PhantomData<T>);
impl<T> Context<T>{fn notify(&mut self){}}
struct Window{ id:u64 }
impl Window{fn window_handle(&self)->u64{self.id}}
struct Entity<T>(Rc<RefCell<T>>);
impl<T> Entity<T>{fn update(&self,_:&mut Context<Chat>,f:impl FnOnce(&mut T,&mut Context<T>)){f(&mut self.0.borrow_mut(),&mut Context(PhantomData))}}
struct InputState{window:u64,text:String}
impl InputState{fn rehost(&mut self,w:&mut Window,_:&mut Context<Self>){self.window=w.id}}
struct Subscription{window:u64}
struct Replies;impl Replies{fn rehost(&mut self,_:WeakEntity<ui::workspace::Workspace>,_:&mut Window,_:&mut Context<Chat>){}}
struct Scroller;impl Scroller{fn remeasure(&mut self,_:&mut Context<Self>){} }
type ComposerExtras=();
struct Binding{answers:HashMap<String,Entity<InputState>>}
struct UserInputDrafts{ texts:HashMap<(String,String),(Entity<InputState>,Subscription)> }
struct Chat{window_handle:u64,extension_activities:HashMap<String,()>,workspace:WeakEntity<ui::workspace::Workspace>,extras:ComposerExtras,composer:Entity<InputState>,_composer_events:Subscription,replies:Replies,codex:Option<Binding>,scroller:Entity<Scroller>,user_input:UserInputDrafts}
impl Chat{fn subscribe_composer(_:&Entity<InputState>,w:&Window,_:&mut Context<Self>)->Subscription{Subscription{window:w.id}}
    pub fn rehost(
        &mut self,
        workspace: WeakEntity<crate::ui::workspace::Workspace>,
        extras: ComposerExtras,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        self.window_handle = window.window_handle();
        self.extension_activities.clear();
        self.workspace = workspace.clone();
        self.extras = extras;
        self.composer
            .update(cx, |composer, cx| composer.rehost(window, cx));
        self._composer_events = Self::subscribe_composer(&self.composer, window, cx);
        self.replies.rehost(workspace, window, cx);
        if let Some(binding) = &mut self.codex {
            for input in binding.answers.values() {
                input.update(cx, |state, cx| state.rehost(window, cx));
            }
        }
        self.scroller
            .update(cx, |scroller, cx| scroller.remeasure(cx));
        cx.notify();
    }
}
fn input(text:&str)->Entity<InputState>{Entity(Rc::new(RefCell::new(InputState{window:1,text:text.into()})))}
#[test] fn moved_chat_rehosts_composer_and_codex_but_leaves_core_answer_in_old_window(){
 let mut chat=Chat{window_handle:1,extension_activities:HashMap::new(),workspace:WeakEntity(PhantomData),extras:(),composer:input("composer"),_composer_events:Subscription{window:1},replies:Replies,codex:Some(Binding{answers:HashMap::from([("codex-q".into(),input("codex answer"))])}),scroller:Entity(Rc::new(RefCell::new(Scroller))),user_input:UserInputDrafts{texts:HashMap::from([(("request".into(),"question".into()),(input("core answer"),Subscription{window:1}))])}};
 chat.rehost(WeakEntity(PhantomData),(),&mut Window{id:2},&mut Context(PhantomData));
 assert_eq!(chat.window_handle,2);assert_eq!(chat.composer.0.borrow().window,2);assert_eq!(chat._composer_events.window,2);
 assert_eq!(chat.codex.as_ref().unwrap().answers["codex-q"].0.borrow().window,2);
 let answer=&chat.user_input.texts[&("request".into(),"question".into())];
 assert_eq!(answer.0.0.borrow().window,1);assert_eq!(answer.1.window,1);assert_eq!(answer.0.0.borrow().text,"core answer");
 println!("AUDIT: Chat/composer/Codex-answer=window2; Core answer+Enter-subscription=window1");
}
