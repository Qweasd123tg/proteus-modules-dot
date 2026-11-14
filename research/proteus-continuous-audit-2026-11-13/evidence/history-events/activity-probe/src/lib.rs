
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
    pub fn set_sessions(
        &mut self,
        sessions: Vec<proteus_contracts::app_protocol::AppSessionSummary>,
        cx: &mut Context<Self>,
    ) {
        self.session_projects
            .retain(|dir, _| !sessions.iter().any(|summary| summary.session_dir == *dir));
        self.sessions
            .retain(|summary| matches!(summary.key, ChatKey::Codex(_)));
        self.sessions
            .extend(crate::conversations::from_proteus(sessions));
        cx.emit(HostEvent::ContextChanged);
    }
    pub fn refresh_sessions(&mut self, cx: &mut Context<Self>) {
        // Metadata refresh must never create a Core for a Codex-only window.
        if self.api().is_none() {
            return;
        }
        if self.sessions_loading {
            self.sessions_stale = true;
            return;
        }
        self.sessions_loading = true;
        let epoch = self.session_catalog_epoch;
        self.call(
            cx,
            |api| Ok(api.sessions()),
            move |this, sessions, cx| {
                this.sessions_loading = false;
                if epoch != this.session_catalog_epoch {
                    this.sessions_stale = false;
                    this.refresh_sessions(cx);
                    return;
                }
                match sessions {
                    Ok(sessions) => {
                        for summary in &sessions {
                            if let Some(activity) = &summary.activity {
                                cx.default_global::<crate::attention::Tracker>()
                                    .baseline(&summary.session_dir, activity.status);
                            }
                        }
                        let known: std::collections::HashSet<_> = sessions
                            .iter()
                            .map(|session| tabs::chat(&session.session_dir))
                            .collect();
                        let open: std::collections::HashSet<_> =
                            this.chats.keys().cloned().collect();
                        this.update_tabs(cx, |layout| {
                            layout.retain(|id| {
                                tabs::chat_dir(id).is_none()
                                    || known.contains(id)
                                    || open.contains(id)
                            });
                        });
                        this.sessions_arrived
                            .get_or_insert_with(std::time::Instant::now);
                        this.set_sessions(sessions, cx);
                    }
                    Err(error) => this.report(format!("{error:#}"), cx),
                }
                if std::mem::take(&mut this.sessions_stale) {
                    this.refresh_sessions(cx);
                }
            },
        );
    }
fn apply_activity(&mut self,tab:&str,session_dir:&PathBuf,activity:&AppSessionActivity,cx:&mut Context<Self>){
                // Repeated copies from other streams carry no change.
                self.attend(session_dir, activity.status, cx);
                self.refresh_subagent_activity(session_dir, activity.status, cx);
                // Every session stream carries every update; only the active
                // chat's copy counts, and a switch reloads the list anyway.
                if self.active_chat.as_deref() != Some(tab) {
                    return;
                }
                match self
                    .sessions
                    .iter_mut()
                    .find(|summary| summary.key.proteus_dir() == Some(session_dir.as_path()))
                {
                    Some(summary) => summary.activity = Some(activity.clone()),
                    None => self.refresh_sessions(cx),
                }
cx.notify();
}

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
mod conversations { use super::*;
#[derive(Clone,Debug)]
pub struct ConversationSummary {
    pub key: ChatKey,
    /// Durable server identity, retained without copying the directory in `key`.
    pub proteus_session_id: Option<uuid::Uuid>,
    pub parent: Option<ChatKey>,
    pub workspace_path: PathBuf,
    pub message_count: usize,
    pub updated_at_ms: Option<u64>,
    pub preview: Option<String>,
    pub activity: Option<AppSessionActivity>,
}
pub fn from_proteus(sessions: Vec<AppSessionSummary>) -> Vec<ConversationSummary> {
    let keys: HashMap<_, _> = sessions
        .iter()
        .map(|summary| {
            (
                summary.session_id,
                ChatKey::Proteus(summary.session_dir.clone()),
            )
        })
        .collect();
    sessions
        .into_iter()
        .map(|summary| ConversationSummary {
            key: ChatKey::Proteus(summary.session_dir),
            proteus_session_id: Some(summary.session_id),
            parent: summary
                .parent_session_id
                .and_then(|id| keys.get(&id).cloned()),
            workspace_path: summary.workspace_path,
            message_count: summary.message_count,
            updated_at_ms: summary.updated_at_ms,
            preview: summary.preview,
            activity: summary.activity,
        })
        .collect()
}
}
