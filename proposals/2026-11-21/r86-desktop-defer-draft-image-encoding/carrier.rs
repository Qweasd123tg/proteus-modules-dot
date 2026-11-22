use crate::{attachments::Attachments,feedback::Feedback};
use proteus_contracts::app_protocol::{AppQueuedUserMessage,http::SendRequest};
use proteus_contracts::domain::{MessageId,RunOptions};
use std::{cell::RefCell,future::Future,pin::pin,sync::{Arc,Mutex},task::{Poll,Waker}};
use serde_json::Value;
pub struct Context {pub notes:usize}
impl Context {fn notify(&mut self){self.notes+=1;}}
pub type App = Context;
pub struct Window;
#[derive(Default)]
struct Input { value:String }
impl Input {
    fn value(&self)->&str{&self.value}
    fn set_value(&mut self,text:String,_:&mut Window,_:&mut Context){self.value=text;}
    fn clean(&mut self,_:&mut Window,_:&mut Context){self.value.clear();}
    fn focus(&mut self,_:&mut Window,_:&mut Context){}
}
#[derive(Default)]
struct Composer(Input);
impl Composer {
    fn read<C>(&self,_:&C)->&Input{&self.0}
    fn update<R>(&mut self,cx:&mut Context,f:impl FnOnce(&mut Input,&mut Context)->R)->R{f(&mut self.0,cx)}
}
struct PendingState {queued_user_messages:Vec<AppQueuedUserMessage>}
struct Session {
    dir:std::path::PathBuf,
    pending:Option<PendingState>,
    feedback:Feedback,
    connected:bool,
}
struct Captured {body:Vec<u8>,request:SendRequest}
impl std::ops::Deref for Captured {
    type Target=SendRequest;
    fn deref(&self)->&SendRequest{&self.request}
}
#[derive(Clone)]
struct Api {wire:Arc<Mutex<Vec<Captured>>>,fail:bool}
impl Api {
    fn send(&self,request:&SendRequest)->anyhow::Result<Value> {
        let body=serde_json::to_vec(request)?;
        let request=serde_json::from_slice(&body)?;
        self.wire.lock().unwrap().push(Captured{body,request});
        if self.fail {anyhow::bail!("fixture refuses")};
        Ok(serde_json::json!({"message_id":uuid::Uuid::from_u128(90)}))
    }
}
type Execute=Box<dyn FnOnce()->anyhow::Result<Value>+Send>;
pub struct Pending {
    id:String,draft_text:String,draft:Attachments,execute:Option<Execute>,
}
fn run_background<F>(future:F)->F::Output
where F:Future, F::Output:Send, F:Send {
    std::thread::scope(|scope|scope.spawn(move||{
        let mut future=pin!(future);
        match future.as_mut().poll(&mut std::task::Context::from_waker(Waker::noop())){
            Poll::Ready(value)=>value,Poll::Pending=>panic!("headless send did not await"),
        }
    }).join().unwrap())
}
pub struct Chat {
    readonly:Option<()>,codex:Option<()>,session:Session,
    composer:Composer,attachments:Attachments,attachments_loading:bool,
    attachment_generation:u64,next_request:u128,api:Option<Api>,
    saved_drafts:Vec<SavedDraft>,pub notices:Vec<String>,pub codex_calls:usize,
}
impl Chat {
    fn send_codex(&mut self,_:&mut Window,_:&mut Context){self.codex_calls+=1}
    fn show_notice(&mut self,text:String,_:&mut Context){self.notices.push(text);}
}
include!("send.inc.rs");
#[path="cases.rs"] mod cases;
pub use cases::run;
