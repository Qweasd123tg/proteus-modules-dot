use crate::carrier::*;
use crate::declarative::protocol::{Content,Outgoing,SurfaceKind};
use anyhow::{Context as _,Result};
use std::{cell::{Cell,RefCell},collections::HashMap,path::PathBuf,rc::Rc,sync::Arc};
mod content_queue;
use content_queue::ContentQueue;
mod io {
    use anyhow::{Context as _,Result};
    use std::io::{self,Write};
    include!("wire.inc.rs");
}
struct Frame {bytes:Vec<u8>,_reservation:Reservation}
struct Reservation;
impl Reservation {
    fn try_grow(&mut self,_:usize,_:&Cell<bool>)->Result<()>{Ok(())}
}
struct Outbound;
impl Outbound {
    fn try_reserve(&self,_:usize,closed:&Cell<bool>)->Result<Reservation>{
        if closed.get(){anyhow::bail!("closed")};Ok(Reservation)
    }
}
#[derive(Default)]
pub struct Capture {
    pub frames: RefCell<Vec<Vec<u8>>>,
    pub payloads: RefCell<Vec<(usize,usize)>>,
    pub errors: RefCell<Vec<String>>,
}
struct Writer(Rc<Capture>);
impl Writer {
    fn try_send(&self,frame:Frame)->Result<()> {
        self.0.frames.borrow_mut().push(frame.bytes);
        Ok(())
    }
}
struct ProcessState {outgoing:Outbound,closed:Cell<bool>,writer:Writer}
impl ProcessState {
    fn stop(&self,error:Option<String>){
        self.closed.set(true);
        if let Some(error)=error {self.writer.0.errors.borrow_mut().push(error);}
    }
}
struct Process {state:ProcessState}
include!("process.inc.rs");
struct Lifetime(bool);
impl Lifetime {fn session(&self)->bool {self.0}}
struct Scope {host:ScopeHost}
struct ScopeHost(Option<PathBuf>);
impl ScopeHost {fn session_dir(&self,_:&App)->Option<PathBuf>{self.0.clone()}}
struct Attached {
    window:u64,
    content:Option<Arc<Content>>,
    surface:SurfaceKind,
    context:String,
    argument:Option<String>,
    queue:ContentQueue,
}
pub struct Runtime {
    views:HashMap<String,Attached>,
    scopes:HashMap<String,Scope>,
    lifetime:Lifetime,
    process:Option<Process>,
    pub capture:Rc<Capture>,
}
impl Runtime {
    pub fn new(id:&str,surface:SurfaceKind,content:Option<Arc<Content>>,addressed:bool)->Self{
        let capture=Rc::new(Capture::default());
        let process=Process{state:ProcessState{outgoing:Outbound,closed:Cell::new(false),writer:Writer(capture.clone())}};
        Self {
            views:HashMap::from([(id.into(),Attached{
                window:2,content,surface,context:"fixture".into(),
                argument:Some("row".into()),queue:ContentQueue::default(),
            })]),
            scopes:HashMap::from([("fixture".into(),Scope{host:ScopeHost(Some("/synthetic/chat".into()))})]),
            lifetime:Lifetime(addressed),process:Some(process),capture,
        }
    }
    fn content_context_for(&self,window:u64,cx:&App)->serde_json::Value{
        assert_eq!(window,2);
        serde_json::json!({"theme":cx.theme.borrow().clone(),"only_preview":"visual fixture"})
    }
    pub fn draw(&mut self,id:&str,cx:&App){self.render(id,cx);}
    pub fn acknowledge(&mut self,id:&str,revision:Option<u64>,cx:&App){self.content_finished(id,revision,cx);}
    pub fn restart(&mut self,id:&str,cx:&App){self.views.get_mut(id).unwrap().queue.reset();self.render(id,cx);}
    pub fn content(&self,id:&str)->Option<&Arc<Content>>{self.views.get(id).unwrap().content.as_ref()}
    pub fn frame_limit()->usize{io::MAX_FRAME}
}
include!("runtime.inc.rs");
