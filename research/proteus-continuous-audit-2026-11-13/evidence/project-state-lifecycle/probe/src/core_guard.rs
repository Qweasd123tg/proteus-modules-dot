
use super::{OpenDocument,Window};
use std::{cell::{Cell,RefCell},rc::Rc,path::{Path,PathBuf},collections::{HashMap,HashSet},time::Instant,marker::PhantomData};
use proteus_tabs as tabs;
use tabs::{TabLayout,ChatSpaces,ChatKey};
use crate::{pending,conversations,proteus_contracts};
use conversations::AgentKind;
#[derive(Clone,Copy,Debug,PartialEq)]enum Status{Ready}
#[derive(Default)]struct Context<T>{_marker:PhantomData<T>}
impl<T> Context<T>{fn notify(&mut self){}fn emit(&mut self,_:HostEvent){}fn default_global<U:Default>(&self)->U{U::default()}}
enum HostEvent{ContextChanged}
#[derive(Clone)]struct Api {id:u64,calls:Rc<Cell<usize>>}
impl Api{fn connection_id(&self)->u64{self.id}fn resume(&self,dir:&Path)->anyhow::Result<Opened>{self.calls.set(self.calls.get()+1);Ok(Opened{session_dir:dir.into(),workspace_path:"/project".into()})}fn sessions(&self)->anyhow::Result<Vec<crate::proteus_contracts::app_protocol::AppSessionSummary>>{self.calls.set(self.calls.get()+1);Ok(vec![])}}
struct Opened{session_dir:PathBuf,workspace_path:PathBuf}
#[derive(Clone)]struct Group{current:Rc<Cell<Option<u64>>>}
impl Group{fn has_core_connection(&self,id:u64)->bool{self.current.get()==Some(id)}fn watch_backend(&self,_:u64,_:(),_:&mut Context<Workspace>) {}}
type Callback=Box<dyn FnOnce(&mut Workspace,&mut Window,&mut Context<Workspace>)>;
struct Workspace{
 api:Option<Api>,windows:Group,status:Status,notice:Option<String>,opening:HashMap<String,Rc<Cell<Option<OpenDocument>>>>,
 spaces:ChatSpaces,layout:TabLayout,chats:HashMap<String,()>,session_projects:HashMap<PathBuf,PathBuf>,
 deleting_sessions:HashSet<ChatKey>,session_catalog_epoch:u64,sessions_loading:bool,sessions_stale:bool,sessions_arrived:Option<Instant>,
 sessions:Vec<conversations::ConversationSummary>,callbacks:Vec<Callback>,calls:Rc<Cell<usize>>,
}
impl Workspace{
 fn fixture()->Self{let mut spaces=ChatSpaces::default();spaces.select("chat:/synthetic/a");let calls=Rc::new(Cell::new(0));Self{api:Some(Api{id:1,calls:calls.clone()}),windows:Group{current:Rc::new(Cell::new(Some(1)))},status:Status::Ready,notice:None,opening:HashMap::new(),layout:spaces.active_layout().clone(),spaces,chats:HashMap::new(),session_projects:HashMap::new(),deleting_sessions:HashSet::new(),session_catalog_epoch:0,sessions_loading:false,sessions_stale:false,sessions_arrived:None,sessions:vec![],callbacks:vec![],calls}}
 fn api(&self)->Option<Api>{self.api.clone()}
 fn reply(&mut self){let cb=self.callbacks.remove(0);cb(self,&mut Window,&mut Context{_marker:PhantomData});}
 fn insert_chat(&mut self,dir:PathBuf,_:&mut Window,_:&mut Context<Self>)->String{let id=tabs::chat(&dir);self.chats.insert(id.clone(),());id}
 fn finish_chat_resume(&mut self,_:&str,_:Option<OpenDocument>,_:&mut Window,_:&mut Context<Self>){}
 fn fail_chat_resume(&mut self,id:&str,msg:String,_:&mut Context<Self>){self.spaces.extract_chat(id);self.layout=self.spaces.active_layout().clone();self.notice=Some(msg)}
 fn report(&mut self,msg:String,_:&mut Context<Self>){self.notice=Some(msg)}
 fn update_tabs(&mut self,_:&mut Context<Self>,change:impl FnOnce(&mut TabLayout)){change(&mut self.layout);self.spaces.save_active(self.layout.clone());}
 fn reconnect(&mut self){self.windows.current.set(Some(2));self.api=Some(Api{id:2,calls:self.calls.clone()});}
 fn stop(&mut self){
  // This models the real shared-slot retirement just above the production
  // per-workspace closure. No real backend is started or terminated.
  let connection=1;let report="synthetic exit";self.windows.current.set(None);
  let this=self;let cx=&mut Context::<Workspace>{_marker:PhantomData};

                if this
                    .api
                    .as_ref()
                    .is_none_or(|api| api.connection_id() != connection)
                {
                    return;
                }
                this.api = None;
                this.notice = Some(report.to_owned().into());
                // A Core failure cannot hide another driver's running turn or Stop.
                this.status = Status::Ready;
                cx.notify();
            
}
fn call<R:Send+'static>(&mut self,_:&mut Context<Self>,job:impl FnOnce(&Api)->anyhow::Result<R>+Send+'static,done:impl FnOnce(&mut Self,R,&mut Context<Self>)+'static){
 let api=self.api.clone().unwrap();let value=job(&api);let exited:Option<()>=None;
 self.callbacks.push(Box::new(move |this,_window,cx|{let result: anyhow::Result<_>=Ok((api,exited,value));

                match result {
                    Ok((api, exited, value)) => {
                        if !this.windows.has_core_connection(api.connection_id()) {
                            return;
                        }
                        this.api = Some(api);
                        if let Some(exited) = exited {
                            this.windows.watch_backend(
                                this.api.as_ref().unwrap().connection_id(),
                                exited,
                                cx,
                            );
                        }
                        match value {
                            Ok(value) => done(this, value, cx),
                            Err(error) => {
                                this.fail_openings(crate::conversations::AgentKind::Proteus, cx);
                                this.report(format!("{error:#}"), cx);
                            }
                        }
                    }
                    Err(error) => {
                        this.fail_openings(crate::conversations::AgentKind::Proteus, cx);
                        this.report(format!("{error:#}"), cx);
                    }
                }
                cx.notify();
            }));
}
fn call_in<R:Send+'static>(&mut self,_:&mut Window,_:&mut Context<Self>,job:impl FnOnce(&Api)->anyhow::Result<R>+Send+'static,done:impl FnOnce(&mut Self,R,&mut Window,&mut Context<Self>)+'static){
 let api=self.api.clone().unwrap();let value=job(&api);let exited:Option<()>=None;
 self.callbacks.push(Box::new(move |this,window,cx|{let result:anyhow::Result<_>=Ok((api,exited,value));

                match result {
                    Ok((api, exited, value)) => {
                        if !this.windows.has_core_connection(api.connection_id()) {
                            return;
                        }
                        this.api = Some(api);
                        if let Some(exited) = exited {
                            this.windows.watch_backend(
                                this.api.as_ref().unwrap().connection_id(),
                                exited,
                                cx,
                            );
                        }
                        match value {
                            Ok(value) => done(this, value, window, cx),
                            Err(error) => {
                                this.fail_openings(crate::conversations::AgentKind::Proteus, cx);
                                this.report(format!("{error:#}"), cx);
                            }
                        }
                    }
                    Err(error) => {
                        this.fail_openings(crate::conversations::AgentKind::Proteus, cx);
                        this.report(format!("{error:#}"), cx);
                    }
                }
                cx.notify();
            }));
}
fn resume_chat(
        &mut self,
        dir: PathBuf,
        open: Option<OpenDocument>,
        window: &mut Window,
        cx: &mut Context<Self>,
    ) {
        let id = tabs::chat(&dir);
        // A double click lands while the first click is still resuming.
        if let Some(pending) = self.opening.get(&id) {
            if let Some(open) = open {
                let previous = pending.get().unwrap_or(open);
                pending.set(Some(OpenDocument {
                    preview: previous.preview && open.preview,
                    focus: previous.focus || open.focus,
                }));
            }
            return;
        }
        let pending = Rc::new(Cell::new(open));
        self.opening.insert(id.clone(), pending.clone());
        self.call_in(
            window,
            cx,
            move |api| Ok(api.resume(&dir)),
            move |this, resumed, window, cx| {
                let Some(open) = pending::take(&mut this.opening, &id, &pending, &this.spaces)
                else {
                    return;
                };
                let opened = match resumed {
                    Ok(opened) => opened,
                    Err(error) => {
                        return this.fail_chat_resume(&id, format!("{error:#}"), cx);
                    }
                };
                this.session_projects
                    .insert(opened.session_dir.clone(), opened.workspace_path);
                let id = this.insert_chat(opened.session_dir, window, cx);
                this.finish_chat_resume(&id, open, window, cx);
            },
        );
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
pub fn fail_openings(&mut self, agent: AgentKind, cx: &mut Context<Self>) {
        let failed: Vec<_> = self
            .opening
            .iter()
            .filter(|(id, _)| {
                crate::tabs::chat_key(id).is_some_and(|key| AgentKind::for_key(&key) == agent)
            })
            .map(|(id, _)| id.clone())
            .collect();
        for id in failed {
            self.opening.remove(&id);
            self.fail_chat_resume(&id, "Подключение к агенту недоступно".into(), cx);
        }
        let deleting = self.deleting_sessions.len();
        self.deleting_sessions
            .retain(|key| AgentKind::for_key(key) != agent);
        if deleting != self.deleting_sessions.len() {
            self.session_catalog_epoch = self.session_catalog_epoch.wrapping_add(1);
        }
    }
}
#[cfg(test)]mod audit{
 use super::*;
 fn start(w:&mut Workspace){w.resume_chat("/synthetic/a".into(),None,&mut Window,&mut Context{_marker:PhantomData});}
 fn stopped_resume()->Workspace{
  let mut w=Workspace::fixture();start(&mut w);assert_eq!(w.calls.get(),1);assert_eq!(w.callbacks.len(),1);
  w.stop();assert!(w.api.is_none());w.reply();assert!(w.callbacks.is_empty());assert!(w.chats.is_empty());
  w.reconnect();for _ in 0..5 {start(&mut w)}
  eprintln!("Core retired completion: opening={}, chats={}, attempted resume requests={}, queued={}",w.opening.len(),w.chats.len(),w.calls.get(),w.callbacks.len());w
 }
 #[test]fn observe_retired_core_resume_leaves_unretriable_opening(){let w=stopped_resume();assert!(w.opening.contains_key("chat:/synthetic/a"));assert_eq!(w.calls.get(),1);assert!(w.chats.is_empty());assert!(w.callbacks.is_empty());}
 #[test]#[ignore]fn regression_retired_core_resume_must_allow_retry(){let w=stopped_resume();assert!(w.calls.get()>1,"new connection must not reuse an unconsumable old opening ticket");}
 fn stopped_catalog()->Workspace{
  let mut w=Workspace::fixture();w.refresh_sessions(&mut Context{_marker:PhantomData});assert!(w.sessions_loading);assert_eq!(w.calls.get(),1);w.stop();w.reply();w.reconnect();for _ in 0..5{w.refresh_sessions(&mut Context{_marker:PhantomData});}
  eprintln!("Core retired catalog: loading={}, stale={}, requests={}, queued={}",w.sessions_loading,w.sessions_stale,w.calls.get(),w.callbacks.len());w
 }
 #[test]fn observe_retired_core_catalog_never_releases_loading(){let w=stopped_catalog();assert!(w.sessions_loading&&w.sessions_stale);assert_eq!(w.calls.get(),1);assert!(w.callbacks.is_empty());}
 #[test]#[ignore]fn regression_retired_catalog_must_allow_refresh(){let w=stopped_catalog();assert!(w.calls.get()>1,"new connection cannot keep coalescing into an abandoned old catalog request");}
 #[test]fn control_live_core_reply_resumes_and_releases_ticket(){let mut w=Workspace::fixture();start(&mut w);w.reply();assert!(w.chats.contains_key("chat:/synthetic/a"));assert!(w.opening.is_empty());}
 #[test]fn control_live_catalog_reply_allows_next_refresh(){let mut w=Workspace::fixture();w.refresh_sessions(&mut Context{_marker:PhantomData});w.reply();assert!(!w.sessions_loading);w.refresh_sessions(&mut Context{_marker:PhantomData});assert_eq!(w.calls.get(),2);}
 #[test]fn control_explicit_opening_failure_releases_ticket(){let mut w=Workspace::fixture();start(&mut w);w.fail_openings(AgentKind::Proteus,&mut Context{_marker:PhantomData});assert!(w.opening.is_empty());}
}
