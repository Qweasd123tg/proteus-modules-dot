from pathlib import Path
import hashlib
root=Path('/workspace/shared/state-install-trace')
s=(root/'src/ui/chats.rs').read_text(); conv=(root/'src/conversations.rs').read_text()
def block(src,marker):
 start=src.index(marker); p=src.index('{',start); level=1; i=p+1
 while level:
  level += (src[i]=='{')-(src[i]=='}');i+=1
 return src[start:i]
set_sessions=block(s,'    pub(super) fn set_sessions(').replace('pub(super)','pub',1)
refresh=block(s,'    pub(super) fn refresh_sessions(').replace('pub(super)','pub',1)
start=s.index('                // Repeated copies from other streams carry no change.')
end=s.index('\n            }\n            ChatEvent::Sent',start)
activity=s[start:end]
summary=block(conv,'pub struct ConversationSummary')
convert=block(conv,'pub fn from_proteus(')
stubs=r'''
#![allow(dead_code,private_interfaces)]
use std::{collections::HashMap,path::{Path,PathBuf},any::{Any,TypeId}};
use proteus_contracts::app_protocol::{AppSessionSummary,AppSessionActivity,AppSessionActivityStatus as Status};
use proteus_tabs::{self as tabs,ChatKey,TabLayout};
use conversations::ConversationSummary;
#[path="/workspace/shared/state-install-trace/src/attention.rs"] mod attention;
struct Context<T>{ globals:HashMap<TypeId,Box<dyn Any>>, _marker:std::marker::PhantomData<T> }
impl<T> Default for Context<T>{fn default()->Self{Self{globals:HashMap::new(),_marker:std::marker::PhantomData}}}
impl<T> Context<T>{
 fn default_global<G:Default+'static>(&mut self)->&mut G{self.globals.entry(TypeId::of::<G>()).or_insert_with(||Box::new(G::default())).downcast_mut().unwrap()}
 fn emit(&mut self,_:HostEvent){} fn notify(&mut self){}
}
enum HostEvent{ContextChanged}
struct Api;
impl Api{fn sessions(&self)->anyhow::Result<Vec<AppSessionSummary>>{panic!("stub captures callback, no real HTTP")}}
type Reply=Box<dyn FnOnce(&mut Workspace,anyhow::Result<Vec<AppSessionSummary>>,&mut Context<Workspace>)>;
#[derive(Default)] struct Workspace{
 sessions:Vec<ConversationSummary>,session_projects:HashMap<PathBuf,PathBuf>,chats:HashMap<String,()>,
 active_chat:Option<String>,sessions_loading:bool,sessions_stale:bool,session_catalog_epoch:u64,
 sessions_arrived:Option<std::time::Instant>,pending:Option<Reply>,calls:usize,layout:TabLayout,
}
impl Workspace{
 fn api(&self)->Option<Api>{Some(Api)}
 fn call(&mut self,_:&mut Context<Self>,_:impl FnOnce(&Api)->anyhow::Result<anyhow::Result<Vec<AppSessionSummary>>>,reply:impl FnOnce(&mut Self,anyhow::Result<Vec<AppSessionSummary>>,&mut Context<Self>)+'static){self.calls+=1;self.pending=Some(Box::new(reply));}
 fn update_tabs(&mut self,_:&mut Context<Self>,f:impl FnOnce(&mut TabLayout)){f(&mut self.layout)}
 fn report(&self,error:String,_:&mut Context<Self>){panic!("{error}")}
 fn attend(&self,p:&Path,status:Status,cx:&mut Context<Self>){cx.default_global::<attention::Tracker>().observe(p,status);}
 fn refresh_subagent_activity(&self,_:&Path,_:Status,_:&mut Context<Self>){}
'''
tests=r'''
}
#[cfg(test)] mod tests{
 use super::*;
 fn summary(activity:AppSessionActivity)->AppSessionSummary{AppSessionSummary::new("/synthetic/background".into(),uuid::Uuid::from_u128(1),"/synthetic".into(),120,Some(1),None).with_activity(activity)}
 #[test] fn stale_http_listing_rolls_back_newer_waiting_input_activity(){
  let mut ws=Workspace{active_chat:Some("active-tab".into()),..Workspace::default()};let mut cx=Context::default();
  let old=summary(AppSessionActivity::from_counts(1,0,0));
  ws.set_sessions(vec![old.clone()],&mut cx);
  ws.refresh_sessions(&mut cx);
  let waiting=AppSessionActivity::from_counts(1,0,1);
  ws.apply_activity("active-tab",&old.session_dir,&waiting,&mut cx);
  assert_eq!(ws.sessions[0].activity.as_ref().unwrap().status,Status::WaitingInput);
  assert!(!ws.sessions_stale,"SSE update does not fence an in-flight catalog");
  let reply=ws.pending.take().unwrap();reply(&mut ws,Ok(vec![old]),&mut cx);
  assert_eq!(ws.sessions[0].activity.as_ref().unwrap().status,Status::Running);
  assert_eq!(ws.sessions[0].activity.as_ref().unwrap().pending_user_inputs,0);
  assert_eq!(ws.calls,1,"no follow-up read scheduled");
  assert!(ws.pending.is_none());
  println!("AUDIT: SSE waiting_input/1 → delayed HTTP running/0; calls={} pending_refresh={}",ws.calls,ws.pending.is_some());
 }
 #[test] fn normal_http_then_sse_order_keeps_waiting_input_control(){
  let mut ws=Workspace{active_chat:Some("active-tab".into()),..Workspace::default()};let mut cx=Context::default();
  let old=summary(AppSessionActivity::from_counts(1,0,0));
  ws.set_sessions(vec![old.clone()],&mut cx);ws.refresh_sessions(&mut cx);
  let reply=ws.pending.take().unwrap();reply(&mut ws,Ok(vec![old.clone()]),&mut cx);
  ws.apply_activity("active-tab",&old.session_dir,&AppSessionActivity::from_counts(1,0,1),&mut cx);
  assert_eq!(ws.sessions[0].activity.as_ref().unwrap().status,Status::WaitingInput);
 }
}
'''
conversations='mod conversations { use super::*;\n#[derive(Clone,Debug)]\n'+summary+'\n'+convert+'\n}\n'
out=Path('/workspace/shared/history-events-evidence/activity-probe/src/lib.rs')
out.write_text(stubs+set_sessions+'\n'+refresh+'\nfn apply_activity(&mut self,tab:&str,session_dir:&PathBuf,activity:&AppSessionActivity,cx:&mut Context<Self>){\n'+activity+'\ncx.notify();\n}\n'+tests+conversations)
Path('/workspace/shared/history-events-evidence/activity-extraction.txt').write_text('Exact extracted complete refresh_sessions/set_sessions methods, visibility only changed pub(super)→pub. Exact Activity match-arm body wrapped as apply_activity. Exact ConversationSummary/from_proteus; actual tabs and attention modules. GPUI context/events stubbed, HTTP callback deferred manually. No real HTTP or GPUI rendering claimed.\n'+ '\n'.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()} {p}' for p in [root/'src/ui/chats.rs',root/'src/conversations.rs',root/'src/attention.rs'])+'\n')
