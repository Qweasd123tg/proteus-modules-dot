// Focused route checks separate from the measured binary. Uses lifted genuine
// code for every read phase and a hostile SessionStorage only for I/O.
pub use proteus_contracts::{contracts,model_standard};
#[path="route/core.rs"] mod core;
use crate::core::{SessionStore,TestIo,TestMode as M,model_context::ModelContextState};
use contracts::{ConversationReader,ConversationSnapshot,ModelContextObservation,SessionStorageFailure};
use model_standard::{CanonicalMessage,MessageRole};
use std::{future::Future,pin::Pin,sync::{Arc,atomic::{AtomicBool,AtomicU64}},task::{Context,Poll,Waker}};
use tokio::sync::Mutex;
use anyhow::Result;
type H=Arc<Mutex<Vec<CanonicalMessage>>>;
type C=Arc<Mutex<ModelContextState>>;
fn reader(candidate:bool,history:H,context:C,store:Option<SessionStore>,resident:bool)->Box<dyn ConversationReader>{
    let resident=Arc::new(AtomicBool::new(resident));let revision=Arc::new(AtomicU64::new(29));
    if candidate{Box::new(core::candidate::TurnConversation{history,context,store,resident,revision})}
    else {Box::new(core::stock::TurnConversation{history,context,store,resident,revision})}
}
fn ctx()->C{Arc::new(Mutex::new(ModelContextState::from_snapshot(vec![ModelContextObservation::Usage{total_tokens:409,last_tokens:9}])))}
fn poll_once<F:Future+?Sized>(f:Pin<&mut F>)->Poll<F::Output>{f.poll(&mut Context::from_waker(Waker::noop()))}
fn report(c:bool,case:&str,n:usize,trace:&[&str]){
    println!("{}",serde_json::json!({"arm":if c{"candidate"}else{"stock"},"case":case,"rows":n,"events":trace,"validated":true}));
}
fn expected_error(mode:M)-> &'static str{match mode{
    M::WrongResponse=>"storage returned an unexpected snapshot response",
    M::WrongSession=>"storage snapshot belongs to another session",
    M::WorkerError=>"session no longer exists",
    M::WrongConversation=>"storage returned an unexpected conversation response",
    _=>panic!("no error expected")
}}
fn err(r:Result<ConversationSnapshot>,m:M){
    let e=r.unwrap_err();assert_eq!(e.to_string(),expected_error(m));
    if m==M::WorkerError{assert_eq!(e.downcast_ref::<SessionStorageFailure>(),Some(&SessionStorageFailure::MissingSession))}
}
async fn resident(c:bool,n:usize,m:M,history:H){
    let context=ctx();
    let (s,io)=SessionStore::fixture(m); let other_handle=s.reopen_fixture();
    let guard=other_handle.park().await;assert!(!s.writer_available());
    let r=reader(c,history.clone(),context.clone(),Some(s.clone()),true);
    let mut f=r.read();assert!(poll_once(f.as_mut()).is_pending());
    assert!(history.try_lock().is_err() && context.try_lock().is_err());assert_eq!(io.n_events(),0);
    drop(guard);let result=f.await;
    assert!(s.writer_available() && history.try_lock().is_ok() && context.try_lock().is_ok());
    match m {
        M::Lease|M::Good|M::ReleaseError=>{
            let out=result.unwrap();assert_eq!(out.revision,if m==M::Lease{41}else{73});
            let h=history.try_lock().unwrap();assert_eq!(out.messages,*h);assert_eq!(out.messages.len(),n);
            assert_eq!(out.model_context,context.try_lock().unwrap().snapshot());assert_eq!(out.messages.capacity(),n);
            if n>0{assert_ne!(h.as_ptr(),out.messages.as_ptr());}
            assert_eq!(io.trace(),if m==M::Lease{vec![]}else{vec!["open","release"]});
        },_=>{err(result,m);assert_eq!(io.trace(),["open"]);}
    }
    assert_eq!(io.free_at_calls(),vec![true;io.n_events()]);
    assert_eq!(io.caller_at_calls(),vec![true;io.n_events()]);
    report(c,&format!("resident-{m:?}"),n,&io.trace());
}
async fn delegated(c:bool,m:M){
    let (s,io)=SessionStore::fixture(m);
    let h=Arc::new(Mutex::new(vec![CanonicalMessage::text(MessageRole::User,"stale-memory")]));
    let context=ctx();let held_context=context.lock().await;
    let held_writer=s.park().await;
    let r=reader(c,h.clone(),context.clone(),Some(s.clone()),false);
    let result=r.read().await;
    // Nonresident never participates in the inner writer/context lock wait.
    let events=match m {
        M::WorkerError|M::WrongResponse|M::WrongSession=>{err(result,m);vec!["open"]},
        M::WrongConversation=>{err(result,m);vec!["open","read","release"]},
        _=>{let out=result.unwrap();assert_eq!(out.revision,73);assert_eq!(out.messages,TestIo::delegated_messages());assert_eq!(out.model_context,vec![ModelContextObservation::HistoryCompacted]);vec!["open","read","release"]}
    };
    assert_eq!(io.trace(),events);assert_eq!(io.caller_at_calls(),vec![false;events.len()]);
    assert_eq!(io.free_at_calls(),vec![false;events.len()]);drop(held_context);drop(held_writer);
    assert!(s.writer_available() && h.try_lock().is_ok() && context.try_lock().is_ok());
    report(c,&format!("nonresident-{m:?}"),1,&events);
}
async fn cancel(c:bool,phase:&str){
    let h=Arc::new(Mutex::new(core::public_rows(1,4)));let cx=ctx();
    let (s,io)=SessionStore::fixture(M::Good);let owned=s.reopen_fixture();
    let r=reader(c,h.clone(),cx.clone(),Some(s.clone()),true);
    match phase{
        "history"=>{let gate=h.lock().await;let mut f=r.read();assert!(poll_once(f.as_mut()).is_pending());assert!(cx.try_lock().is_ok() && s.writer_available());drop(f);drop(gate);},
        "context"=>{let gate=cx.lock().await;let mut f=r.read();assert!(poll_once(f.as_mut()).is_pending());assert!(h.try_lock().is_err() && s.writer_available());drop(f);assert!(h.try_lock().is_ok());drop(gate);},
        "writer"|"granted-before-repoll"=>{
            let gate=owned.park().await;let mut f=r.read();assert!(poll_once(f.as_mut()).is_pending());assert!(h.try_lock().is_err() && cx.try_lock().is_err());
            if phase=="writer"{drop(f);assert!(h.try_lock().is_ok() && cx.try_lock().is_ok());drop(gate);}
            else {drop(gate);drop(f);}
        },
        _=>unreachable!()
    }
    assert!(h.try_lock().is_ok() && cx.try_lock().is_ok() && s.writer_available());
    assert_eq!(io.n_events(),0);assert_eq!(r.read().await.unwrap().revision,73);
    assert_eq!(io.trace(),["open","release"]);report(c,&format!("cancel-{phase}-then-retry"),1,&io.trace());
}
async fn queued(c:bool){
    let h=Arc::new(Mutex::new(core::public_rows(1,4)));let cx=ctx();let (s,io)=SessionStore::fixture(M::Lease);
    let gate=s.park().await;
    let a=reader(c,h.clone(),cx.clone(),Some(s.clone()),true);
    let b=reader(c,h.clone(),cx.clone(),Some(s.clone()),true);
    let mut f=a.read();assert!(poll_once(f.as_mut()).is_pending());
    let mut g=b.read();assert!(poll_once(g.as_mut()).is_pending());
    drop(gate);drop(f);
    assert_eq!(g.await.unwrap().revision,41);assert!(h.try_lock().is_ok() && cx.try_lock().is_ok() && s.writer_available());
    assert_eq!(io.n_events(),0);report(c,"cancel-granted-queued-sibling-resumes",1,&io.trace());
}
async fn no_store(c:bool){
    let h=Arc::new(Mutex::new(core::public_rows(1,4)));let cx=ctx();
    let x=reader(c,h.clone(),cx.clone(),None,true).read().await.unwrap();assert_eq!(x.revision,29);assert_eq!(x.messages,*h.try_lock().unwrap());
    assert_eq!(x.model_context,cx.try_lock().unwrap().snapshot());report(c,"no-store",1,&[]);
    let r=reader(c,h.clone(),cx.clone(),None,false);
    let gate=cx.lock().await;
    assert_eq!(r.read().await.unwrap_err().to_string(),"nonresident history has no session store");drop(gate);
    assert!(h.try_lock().is_ok() && cx.try_lock().is_ok());report(c,"nonresident-no-store",1,&[]);
}
async fn checks(){
    for n in [0,1,5000,50000] {
        // Both implementations read the same genuine immutable fixture, IDs included.
        let shared=Arc::new(Mutex::new(core::public_rows(n,4)));
        for c in [false,true]{
            for m in [M::Lease,M::Good]{resident(c,n,m,shared.clone()).await;}
            if n==1{
                for m in [M::WrongResponse,M::WrongSession,M::WorkerError,M::ReleaseError]{resident(c,n,m,shared.clone()).await;}
                for m in [M::Good,M::WorkerError,M::WrongResponse,M::WrongSession,M::ReleaseError,M::WrongConversation]{delegated(c,m).await;}
                for phase in ["history","context","writer","granted-before-repoll"]{cancel(c,phase).await;}
                queued(c).await;no_store(c).await;
            }
        }
    }
}
fn main(){tokio::runtime::Builder::new_current_thread().build().unwrap().block_on(checks())}
