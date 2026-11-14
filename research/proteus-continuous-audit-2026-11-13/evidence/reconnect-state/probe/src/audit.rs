use super::*;
use std::{time::{Duration,Instant},io::Write,net::TcpStream};
fn options(name:&str)->LaunchOptions{
 let configured=std::env::var_os("PROTEUS_BIN").expect("Set PROTEUS_BIN to probe/fixture_core.py");
 assert_eq!(PathBuf::from(configured).canonicalize().unwrap(),PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixture_core.py").canonicalize().unwrap(),"This probe may launch only its own synthetic peer");
 let nonce=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
 let workspace=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("runs").join(format!("{name}-{nonce}"));std::fs::create_dir_all(&workspace).unwrap();
 LaunchOptions{workspace,target:launch::Target::Spawn{profile:None}}
}
fn launches(options:&LaunchOptions)->u32{std::fs::read_to_string(options.workspace.join("launches")).unwrap().parse().unwrap()}
fn terminate_fixture(api:&Api){
 let addr=api.origin().strip_prefix("http://").unwrap();let mut s=TcpStream::connect(addr).unwrap();
 s.write_all(b"POST /fixture/exit HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}").unwrap();
}
fn exit_report(rx:async_channel::Receiver<String>)->String{
 let end=Instant::now()+Duration::from_secs(7);loop{if let Ok(r)=rx.try_recv(){return r};assert!(Instant::now()<end,"backend watcher did not report fixture exit");std::thread::sleep(Duration::from_millis(10))}
}
fn shutdown(group:&WindowGroup){let backend=group.core_slot().lock().unwrap().take().and_then(|c|c.backend);if let Some(b)=backend{b.shutdown()}}
fn receive_connected(view:&Entity<Chat>){let mut c=view.0.borrow_mut();if c.session.connected{return}let event=c.receive();assert!(matches!(event,PumpItem::Connected));c.observe(event)}
fn receive_disconnected(view:&Entity<Chat>){let mut c=view.0.borrow_mut();let event=c.receive();assert!(matches!(event,PumpItem::Disconnected(_)));c.observe(event);assert!(!c.session.connected)}
fn get_chat(workspace:&Entity<Workspace>,key:&ChatKey)->Entity<Chat>{workspace.0.borrow().chats[&key.tab_id()].view.clone()}
fn open(workspace:&Entity<Workspace>,key:&ChatKey){workspace.0.borrow_mut().open_chat(key.clone(),OpenDocument{preview:false,focus:true},&mut Window,&mut Context::default())}

fn contested_exit()->(u32,u64,u64){
 let options=options("contested-exit");let group=WindowGroup::default();let slot=group.core_slot();
 let (old,exited)=core(&slot,&options).unwrap();assert!(old.sessions().unwrap().is_empty());
 let workspace=Workspace::fixture(group.clone(),old.clone());
 terminate_fixture(&old);let report=exit_report(exited.unwrap());assert!(report.contains("17"));
 // The background checkout of this same shared slot can overlap UI exit
 // delivery. Hold the real MutexGuard across exactly that deterministic window.
 let (locked,ready)=std::sync::mpsc::channel();let (release,wait)=std::sync::mpsc::channel();
 let held_slot=slot.clone();let holder=std::thread::spawn(move||{let _guard=held_slot.lock().unwrap();locked.send(()).unwrap();wait.recv().unwrap();});ready.recv().unwrap();
 group.server_stopped(old.connection_id(),&report,&mut App);
 release.send(()).unwrap();holder.join().unwrap();
 let mut reused=0;
 for _ in 0..5 {let (api,watcher)=core(&slot,&options).unwrap();reused=api.connection_id();assert!(watcher.is_none());assert!(api.sessions().is_err());}
 assert!(workspace.0.borrow().api.is_some(),"no per-window retirement took place either");
 let count=launches(&options);eprintln!("contested exit: old={}, next={}, launches={}, failed retry calls=5",old.connection_id(),reused,count);
 shutdown(&group);(count,old.connection_id(),reused)
}
#[test]fn observe_backend_exit_contention_keeps_dead_lease(){let (count,old,reused)=contested_exit();assert_eq!(count,1);assert_eq!(old,reused)}
#[test]#[ignore]fn regression_backend_exit_must_not_be_lost_to_mutex_contention(){let (count,old,reused)=contested_exit();assert!(count>1&&old!=reused,"a confirmed dead process must stop being the current backend after temporary contention ends")}
#[test]fn control_uncontended_exit_restarts_backend(){
 let options=options("uncontended-exit");let group=WindowGroup::default();let slot=group.core_slot();let (old,exited)=core(&slot,&options).unwrap();
 let workspace=Workspace::fixture(group.clone(),old.clone());terminate_fixture(&old);let report=exit_report(exited.unwrap());group.server_stopped(old.connection_id(),&report,&mut App);
 assert!(slot.lock().unwrap().is_none());assert!(workspace.0.borrow().api.is_none());let (new,_)=core(&slot,&options).unwrap();assert_ne!(new.connection_id(),old.connection_id());assert!(new.sessions().unwrap().is_empty());assert_eq!(launches(&options),2);shutdown(&group);
}
#[test]fn control_late_old_exit_preserves_replacement(){
 let group=WindowGroup::default();let old=Api::new("http://127.0.0.1:1","synthetic-old");let new=Api::new("http://127.0.0.1:1","synthetic-new");group.set_core(new.clone(),None);group.server_stopped(old.connection_id(),"old report",&mut App);assert!(group.has_core_connection(new.connection_id()));
}
#[test]fn observe_identity_check_treats_lock_contention_as_wrong_generation(){
 let group=WindowGroup::default();let api=Api::new("http://127.0.0.1:1","synthetic");group.set_core(api.clone(),None);assert!(group.has_core_connection(api.connection_id()));let slot=group.core_slot();let guard=slot.lock().unwrap();assert!(!group.has_core_connection(api.connection_id()));drop(guard);assert!(group.has_core_connection(api.connection_id()));
}

fn existing_chat_after_restart()->(u64,u64,bool,usize){
 let options=options("old-chat-restart");let group=WindowGroup::default();let slot=group.core_slot();let (old,exited)=core(&slot,&options).unwrap();let workspace=Workspace::fixture(group.clone(),old.clone());
 let a=ChatKey::Proteus(options.workspace.join("session-a"));open(&workspace,&a);let chat_a=get_chat(&workspace,&a);receive_connected(&chat_a);
 terminate_fixture(&old);let report=exit_report(exited.unwrap());receive_disconnected(&chat_a);group.server_stopped(old.connection_id(),&report,&mut App);assert!(workspace.0.borrow().api.is_none());
 let (new,_)=core(&slot,&options).unwrap();assert_ne!(old.origin(),new.origin());assert_ne!(old.token(),new.token());assert!(new.sessions().unwrap().is_empty());
 // The native Workspace::call/::call_in success path installs this Api.
 // Here we perform that assignment directly: no GPUI async scheduler/paint.
 workspace.0.borrow_mut().api=Some(new.clone());
 let b=ChatKey::Proteus(options.workspace.join("session-b"));open(&workspace,&b);let chat_b=get_chat(&workspace,&b);receive_connected(&chat_b);assert_eq!(chat_b.0.borrow().api.as_ref().unwrap().connection_id(),new.connection_id());
 open(&workspace,&a);let before=workspace.0.borrow().resume_calls;for _ in 0..3{open(&workspace,&a)}
 assert_eq!(workspace.0.borrow().resume_calls,before,"existing-chat open bypasses resume");
 {
  let mut w=workspace.0.borrow_mut();w.insert_chat(a.proteus_dir().unwrap().into(),&mut Window,&mut Context::default());
  // close_tab's model effect, followed by the real sync_chats method.
  w.layout.close(&a.tab_id());let layout=w.layout.clone();w.spaces.save_active(layout.clone());w.sync_chats(&layout,&mut Context::default());
  assert!(w.chats.contains_key(&a.tab_id()),"root owner intentionally retained when its UI tab is closed");
 }
 open(&workspace,&a);assert!(Rc::ptr_eq(&chat_a.0,&get_chat(&workspace,&a).0));
 receive_disconnected(&chat_a); // Real scheduled retry to the dead old origin.
 let old_id=chat_a.0.borrow().api.as_ref().unwrap().connection_id();let connected=chat_a.0.borrow().session.connected;
 assert!(chat_a.0.borrow().api.as_ref().unwrap().sessions().is_err());
 let req=std::fs::read_to_string(options.workspace.join("requests.jsonl")).unwrap();let new_a=req.lines().filter(|l|{let v:serde_json::Value=serde_json::from_str(l).unwrap();v["generation"]==2&&(v["path"].as_str().unwrap().contains("session-a")||v["session_dir"].as_str().is_some_and(|s|s.ends_with("session-a")))}).count();
 eprintln!("restarted Core: new={}, retained old chat={}, connected={}, new-backend requests for session-a={}, launches={}",new.connection_id(),old_id,connected,new_a,launches(&options));
 drop(chat_a);drop(chat_b);drop(workspace);shutdown(&group);(new.connection_id(),old_id,connected,new_a)
}
#[test]fn observe_existing_chat_remains_bound_to_dead_core_after_successful_restart(){let (new,chat,connected,requests)=existing_chat_after_restart();assert_ne!(new,chat);assert!(!connected);assert_eq!(requests,0)}
#[test]#[ignore]fn regression_existing_chat_must_rebind_after_successful_core_restart(){let (new,chat,connected,requests)=existing_chat_after_restart();assert!(new==chat&&connected&&requests>0,"reopening the retained root should restore its stream against the live replacement Core")}
