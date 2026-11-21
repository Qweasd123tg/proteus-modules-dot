use super::*;
use crate::ledger::{self,Work};
use proteus_contracts::app_protocol::{AppSessionActivity,AppSessionActivityStatus};
use serde_json::{Value,json};
use std::path::Path;

const KNOWN:&str="chat:/sessions/живой";
const OPEN:&str="chat:/sessions/open-only";
const CLOSED:&str="chat:/sessions/closed-restored";
const PIN_GONE:&str="chat:/sessions/unknown-pin";
const DOC:&str="files:chat:/document";
const CODEX:&str="codex:remote:chat:/opaque";
const PREVIEW:&str="files:preview";
const HIDDEN_DOC:&str="unavailable:document";
const CLOSED_DOC:&str="files:earlier-reopen";
const CANON:&str="chat:/sessions/raw/path";
const REP:&str="chat:/sessions/raw//path";
const DOT:&str="chat:/sessions/raw/./path";
const TRAILING:&str="chat:/sessions/raw/path/";
const REPLACEMENT:&str="chat:/sessions/split-�";
const EMPTY:&str="chat:";

fn summary(dir:impl Into<PathBuf>,n:usize)->AppSessionSummary{
    let mut row=AppSessionSummary::new(dir.into(),uuid::Uuid::from_u128(n as u128+100),
            "/fixture/workspace".into(),n,Some(1_777_777_000_000+n as u64),Some(format!("Session {n} — тест")));
    if n==0 {
        row=row.with_activity(AppSessionActivity::from_counts(1,0,0));
    } else if n==1 {
        row.parent_session_id=Some(uuid::Uuid::from_u128(100));
    }
    row
}
fn through_wire(rows:Vec<AppSessionSummary>)->Vec<AppSessionSummary>{
    let wire=serde_json::to_vec(&rows).unwrap();
    let incoming:Vec<AppSessionSummary>=serde_json::from_slice(&wire).unwrap();
    assert_eq!(serde_json::to_vec(&incoming).unwrap(),wire);
    incoming
}
fn first_layout(extra:&[&str])->TabLayout{
    let mut l=TabLayout::default();
    for id in [KNOWN,OPEN,CLOSED,PIN_GONE,CODEX,DOC,HIDDEN_DOC,CLOSED_DOC].into_iter().chain(extra.iter().copied()){
        l.open_in(id,tabs::PaneId(0),|_|false);
    }
    l.close(CLOSED_DOC);
    for pin in [KNOWN,OPEN,PIN_GONE] {l.set_pinned(pin,true);}
    l.split(DOC,tabs::PaneId(0),tabs::Edge::Right);
    assert_eq!(l.pane_count(),2);
    l.open_preview(PREVIEW, |_| false);
    let chat=l.pane_of(KNOWN).unwrap();
    l.activate(chat,CLOSED);
    l.activate(chat,OPEN);
    l.activate(chat,PIN_GONE);
    l.focus(chat);
    l.validate().unwrap();
    assert_eq!(l.closed_ids().collect::<Vec<_>>(),[CLOSED_DOC]);
    l
}
fn workspace(extra:&[&str])->Workspace{
    let layout=first_layout(extra);
    let spaces=ChatSpaces::from_layout(layout.clone());
    let mut ws=Workspace{layout,spaces,has_api:true,..Workspace::default()};
    ws.chats.insert(OPEN.into(),());
    ws.documents.insert(DOC.into(),());
    ws.documents.insert(HIDDEN_DOC.into(),());
    ws.document_titles.insert(DOC.into(),"existing document".into());
    ws.document_titles.insert(HIDDEN_DOC.into(),"unavailable document".into());
    let summary=crate::agents::codex::Summary{
        id:"remote:chat:/opaque".into(),title:"Existing Codex".into(),..Default::default()
    };
    ws.sessions.push(crate::conversations::from_codex(&summary));
    ws.session_projects.insert("/sessions/живой".into(),"/replaced-by-catalog".into());
    ws.session_projects.insert("/sessions/still-pending".into(),"/keep-this-one".into());
    ws
}
fn catalog(n:usize,repeat:bool)->Vec<AppSessionSummary>{
    assert!(n>1);
    let mut v=vec![summary("/sessions/живой",0),summary("/sessions/child",1)];
    for i in 2..n {
        let dir=if repeat && i==n-1 {"/sessions/живой".to_string()} else {format!("/sessions/archive/папка-{i:03}/log")};
        v.push(summary(dir,i));
    }
    through_wire(v)
}
fn oracle(layout:&TabLayout,keep:&[&str])->TabLayout{
    let mut known=layout.clone();
    known.retain(|id|id!=HIDDEN_DOC);
    known.retain(|id|keep.contains(&id));
    known.validate().unwrap();
    known
}
fn work(name:&str,candidate:bool,count:usize,owned:usize){
    let expected=if candidate{Work{prefixed:0,borrowed:count-owned,owned}}
                         else{Work{prefixed:count,borrowed:0,owned:0}};
    assert_eq!(ledger::observed(),expected,"{name}");
    eprintln!("WORK {name} prefixed={} borrowed={} owned={}",expected.prefixed,expected.borrowed,expected.owned);
}
fn assert_layout(name:&str,ws:&Workspace,expected:&TabLayout,cx:&Context<Workspace>){
    assert_eq!(&ws.layout,expected,"{name} partialeq incl. non-persisted history");
    assert_eq!(ws.spaces.active_layout(),expected);
    let persisted=ws.windows.0.last().unwrap();
    assert_eq!(persisted.0,42);
    assert_eq!(persisted.1,ws.spaces);
    assert_eq!(serde_json::to_vec(&persisted.1).unwrap(),serde_json::to_vec(&ws.spaces).unwrap());
    assert_eq!(ws.synced.last().unwrap(),expected);
    assert_eq!(&ws.tab_motion.0.last().unwrap().1,expected);
    assert_eq!(ws.layout.closed_ids().collect::<Vec<_>>(),[CLOSED_DOC]);
    assert!(ws.layout.is_pinned(OPEN));
    assert!(!ws.layout.contains(PIN_GONE));
    assert!(ws.layout.contains(CODEX));
    assert!(ws.layout.contains(DOC));
    assert!(!ws.documents.contains_key(HIDDEN_DOC));
    assert!(!ws.document_titles.contains_key(HIDDEN_DOC));
    assert_eq!(ws.document_titles.get(DOC).unwrap(),"existing document");
    assert_eq!(&cx.events[cx.events.len()-2..], [HostEvent::NavigationChanged,HostEvent::ContextChanged]);
    println!("PASS {name} layout={} spaces={} closed={:?} records={} notify={}",
        serde_json::to_string(&ws.layout).unwrap(),serde_json::to_string(&ws.spaces).unwrap(),
        ws.layout.closed_ids().collect::<Vec<_>>(),ws.sessions.len(),cx.notifications);
}
fn complete(name:&str, rows:Vec<AppSessionSummary>, extras:&[&str], keep:&[&str], n_owned:usize, candidate:bool){
    let count=rows.len();
    let mut ws=workspace(extras);
    let mut cx=Context::default();
    let oracle=oracle(&ws.layout,keep);
    let expected_from_catalog=crate::conversations::from_proteus(rows.clone());
    let existing_codex=ws.sessions[0].clone();
    let releases_known=rows.iter().any(|r|r.session_dir==Path::new("/sessions/живой"));
    ws.work.push_back(Ok(rows));
    ledger::reset();
    ws.refresh_sessions(&mut cx);
    assert!(ws.sessions_loading);
    assert_eq!(ws.calls,1);
    assert_eq!(ledger::observed(),Work::default());
    assert!(ws.sessions_arrived.is_none());
    ws.finish(&mut cx);
    work(name,candidate,count,n_owned);
    assert!(ws.sessions_arrived.is_some() && !ws.sessions_loading && !ws.sessions_stale);
    assert_eq!(ws.sessions[0],existing_codex);
    assert_eq!(&ws.sessions[1..],expected_from_catalog);
    assert_eq!(ws.session_projects.contains_key(Path::new("/sessions/живой")),!releases_known);
    assert!(ws.session_projects.contains_key(Path::new("/sessions/still-pending")));
    if releases_known {
        assert_eq!(cx.default_global::<attention::Tracker>().observe(Path::new("/sessions/живой"),AppSessionActivityStatus::Idle),Some(attention::Attention::Finished));
    }
    assert_eq!(cx.events.len(),2);
    assert_layout(name,&ws,&oracle,&cx);
}
#[cfg(unix)]
fn odd_bytes(candidate:bool){
    use std::{ffi::OsString,os::unix::ffi::OsStringExt};
    let invalid=PathBuf::from(OsString::from_vec(b"/sessions/split-\xff".to_vec()));
    assert!(invalid.to_str().is_none());
    assert_eq!(tabs::chat(&invalid),REPLACEMENT);
    // Baseline also collides with a distinct valid real U+FFFD spelling.
    let valid=PathBuf::from("/sessions/split-�");
    let both=vec![summary(invalid,0),summary(valid,1)];
    assert!(serde_json::to_vec(&both).is_err(),"not a synthetic normal JSON path");
    complete("unix-invalid-code-unit-collision",both,&[REPLACEMENT],&[OPEN, DOC, CODEX, PREVIEW, REPLACEMENT],1,candidate);
}
fn lifecycle(candidate:bool){
    let mut ws=workspace(&[]);
    let mut cx=Context::default();
    ws.has_api=false;
    ws.refresh_sessions(&mut cx);
    assert_eq!(ws.calls,0);
    println!("PASS no Core connection does not fetch");
    ws.has_api=true;
    let initial=ws.layout.clone();
    ws.work.push_back(Ok(through_wire(vec![summary("/sessions/would-be-stale",0)])));
    ws.work.push_back(Err(anyhow::anyhow!("fixture network error")));
    ws.work.push_back(Ok(catalog(80,false)));
    ws.work.push_back(Ok(through_wire(vec![])));
    ledger::reset();
    ws.refresh_sessions(&mut cx);
    ws.refresh_sessions(&mut cx);
    assert_eq!(ws.calls,1);
    assert!(ws.sessions_stale);
    ws.session_catalog_epoch+=1;
    ws.finish(&mut cx); // stale reply cannot commit; issues fresh request
    assert_eq!(ws.calls,2);
    assert!(ws.sessions_loading && !ws.sessions_stale);
    assert_eq!(ws.layout,initial);
    assert_eq!(ledger::observed(),Work::default());
    assert!(cx.events.is_empty() && ws.sessions_arrived.is_none());
    println!("PASS stale generation skipped before any projection");
    ws.refresh_sessions(&mut cx); // mark pending during request that will fail
    assert!(ws.sessions_stale);
    ws.finish(&mut cx); // preserves report, then reruns exactly once
    assert_eq!(ws.errors,["fixture network error"]);
    assert_eq!(ws.calls,3);
    assert_eq!(ws.layout,initial);
    assert_eq!(ledger::observed(),Work::default());
    assert!(cx.events.is_empty() && ws.sessions_arrived.is_none());
    println!("PASS failed current reply reports and leaves existing layout/catalog");
    ws.refresh_sessions(&mut cx);
    ws.refresh_sessions(&mut cx);
    assert!(ws.sessions_stale);
    ws.finish(&mut cx); // accepted 80, then one coalesced follow-up
    work("accepted-current-after-stale-and-error",candidate,80,0);
    let expected=oracle(&initial,&[KNOWN,OPEN,DOC,CODEX,PREVIEW]);
    assert_layout("accepted-current-after-stale-and-error",&ws,&expected,&cx);
    assert_eq!(ws.calls,4);
    assert!(ws.sessions_loading && !ws.sessions_stale);
    let arrived=ws.sessions_arrived;
    ledger::reset();
    ws.finish(&mut cx);
    work("coalesced-empty-current",candidate,0,0);
    let expected=oracle(&expected,&[OPEN,DOC,CODEX,PREVIEW]);
    assert_layout("coalesced-empty-current",&ws,&expected,&cx);
    assert_eq!(ws.sessions_arrived,arrived);
    assert_eq!(ws.calls,4);
    assert_eq!(ws.windows.0.len(),2);
    assert!(ws.pending.is_empty() && ws.work.is_empty() && !ws.sessions_loading && !ws.sessions_stale);
    assert_eq!(ws.sessions.len(),1);
    assert_eq!(cx.events.as_slice(),&[HostEvent::NavigationChanged,HostEvent::ContextChanged,HostEvent::NavigationChanged,HostEvent::ContextChanged]);
    println!("PASS refresh/coalesce generation lifecycle callbacks exactly two commits");
}
pub(crate) fn run(candidate:bool) {
    complete("normal-80",catalog(80,false),&[],&[KNOWN,OPEN,DOC,CODEX,PREVIEW],0,candidate);
    complete("normal-256-with-duplicate",catalog(256,true),&[],&[KNOWN,OPEN,DOC,CODEX,PREVIEW],0,candidate);
    complete("normal-empty",through_wire(vec![]),&[],&[OPEN,DOC,CODEX,PREVIEW],0,candidate);
    complete("normal-single",through_wire(vec![summary("/sessions/живой",0)]),&[],&[KNOWN,OPEN,DOC,CODEX,PREVIEW],0,candidate);
    let exact=through_wire(vec![summary("/sessions/raw//path",0),summary("",1)]);
    assert_eq!(tabs::chat(&exact[0].session_dir),REP);
    assert_eq!(tabs::chat(&exact[1].session_dir),EMPTY);
    assert_eq!(exact[0].session_dir,Path::new("/sessions/raw/path"));
    complete("textual-path-alias-and-bare-prefix",exact,&[CANON,REP,DOT,TRAILING,EMPTY],&[REP,EMPTY,OPEN,DOC,CODEX,PREVIEW],0,candidate);
    #[cfg(unix)] odd_bytes(candidate);
    lifecycle(candidate);
}
