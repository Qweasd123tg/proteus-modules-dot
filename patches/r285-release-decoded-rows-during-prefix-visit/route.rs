#![allow(dead_code,unused_imports,unreachable_patterns)]
use anyhow::{Result,bail,ensure};use serde::{Serialize,Deserialize};use serde_json::{Value,json};
use std::{cell::{Cell,RefCell},collections::{BTreeMap,HashMap,HashSet},path::{Path,PathBuf},sync::{Arc,Mutex,atomic::{AtomicBool,Ordering}}};
use uuid::Uuid;
pub use proteus_contracts::{contracts,domain,model_standard};
use proteus_contracts::{app_protocol::*,contracts::*,domain::*,model_standard::*,storage::journal::*};
use proteus_contracts::contracts::{SessionStorageRequest as Request,SessionStorageResponse as Response};
mod core;mod snap;use snap::{RemoteJournalCursor,RemoteJournalSnapshot,RemoteValidatedRead};type JournalReadSnapshot=RemoteJournalSnapshot;
mod stage;use stage::{DisplayRecords,DisplayRecordWriter,is_display_kind};mod render;
mod prepared;use prepared::PreparedSession;mod read;mod meter;
thread_local!{
 static EVENTS:RefCell<Vec<String>>=const{RefCell::new(Vec::new())};
 static FINAL:Cell<bool>=const{Cell::new(false)};
 static UNSTAGED:Cell<bool>=const{Cell::new(false)};
 static PREFIXING:Cell<bool>=const{Cell::new(false)};
 static CHANGED:Cell<bool>=const{Cell::new(false)};
 static F:Cell<&'static str>=const{Cell::new("")};
 static STAGE:Cell<(usize,u64,bool)>=const{Cell::new((0,0,false))};
}
fn trace(s:String){EVENTS.with(|t|t.borrow_mut().push(s))}
fn ready_for_final(){assert!(!FINAL.replace(true));}
fn observe_render(s:&mut RemoteJournalSnapshot){
 STAGE.set(snap::stage_status(s));trace("Render".into());
}
fn bytes(v:&impl Serialize)->Vec<u8>{serde_json::to_vec(v).unwrap()}
fn sha(v:&[u8])->String{ring::digest::digest(&ring::digest::SHA256,v).as_ref().iter().map(|v|format!("{v:02x}")).collect()}
fn history_record(ms:Vec<CanonicalMessage>,seq:u64,replace:bool,invalid:bool)->JournalRecord{
 JournalRecord{schema_version:JOURNAL_SCHEMA_VERSION,record_id:Uuid::from_u128(99+seq as u128),session_seq:seq,timestamp_ms:1001,session_id:SESSION,execution_id:None,thread_id:Some(THREAD),turn_id:None,entry:JournalEntry::HistoryMutated(HistoryMutated{previous_revision:seq-1,new_revision:if invalid{1+seq}else{seq},mutation:if replace{HistoryMutationKind::Replace}else{HistoryMutationKind::Append},messages:ms,compaction:None,tool_results:vec![]})}
}
fn records(n:usize,mixed:bool,fault:&str)->Arc<Vec<JournalRecord>>{
 if n==0{return Arc::new(vec![])}
 let mut ms=seed(n,4);
 for (i,m) in ms.iter_mut().enumerate(){
  m.id=Uuid::from_u128(0x100000+i as u128);m.parts[0].part_id=Uuid::from_u128(0x200000+i as u128);
  if mixed && i%5==0{m.metadata=json!({"ключ\n":[true,{},-0.25,"\0🦀\""]});}
  if mixed && i%7==0 {
   m.parts.push(CanonicalPart::new(PartProvenance::Runtime,PartScope::Conversation,ContentPart::Text{text:"second canonical part".into()}).with_id(Uuid::from_u128(0x300000+i as u128)));
  }
 }
 if fault=="many-single"{
  Arc::new(ms.into_iter().enumerate().map(|(i,m)|history_record(vec![m],i as u64+1,false,false)).collect())
 }else if fault=="reset"{
  Arc::new(vec![history_record(ms[..3].to_vec(),1,false,false),history_record(ms,2,true,false)])
 }else{Arc::new(vec![history_record(ms,1,false,fault=="validator")])}
}
fn canonical(src:&[JournalRecord])->Vec<&CanonicalMessage>{
 let mut v=Vec::new();
 for rec in src{if let JournalEntry::HistoryMutated(h)=&rec.entry{
  if h.mutation==HistoryMutationKind::Replace{v.clear();}
  v.extend(&h.messages);
 }}
 v
}
fn identity_set_oracle(src:&[JournalRecord])->(HashSet<Uuid>,HashSet<Uuid>){
 let mut messages=HashSet::new();let mut parts=HashSet::new();
 for rec in src{if let JournalEntry::HistoryMutated(h)=&rec.entry{
  messages.extend(h.messages.iter().map(|m|m.id));
  parts.extend(h.messages.iter().flat_map(|m|m.parts.iter().map(|p|p.part_id)));
 }}
 (messages,parts)
}
fn verify_rows(rows:&[AppTranscriptMessage],source:&[&CanonicalMessage],offset:usize){
 for (i,row) in rows.iter().enumerate(){
  let m=source[offset+i];assert_eq!(row.message_id,Some(m.id));assert_eq!(row.timestamp_ms,Some(1001));
  assert_eq!(row.role,if (offset+i)%2==0{"user"}else{"assistant"});
  let parts=m.parts.iter().map(|p|match &p.payload{ContentPart::Text{text}=>text.as_str(),_=>unreachable!()}).collect::<Vec<_>>();
  assert_eq!(row.text,parts.join("\n"));assert!(!row.streaming && row.images.is_empty() && row.tool.is_none());
 }
}
fn get_trace()->Vec<String>{EVENTS.with(|e|e.borrow().clone())}
fn empty_trace(){EVENTS.with(|t|t.borrow_mut().clear());}
fn get_error(fault:&str)->Option<&'static str>{
 Some(match fault{
 "late-lf"=>"incomplete transcript staging record",
 "late-decode"=>"key must be a string",
 "late-count"=>"transcript staging record count changed",
 "late-unstaged"=>"storage record page made no progress",
 "validator"=>"history revision must increment",
 "unknown-named"=>"history revision changed; refresh the session snapshot",
 "final-hash"=>"history source changed during recovery; refresh the session snapshot",
 _=>return None
 })
}
fn expect_render(fault:&str)->bool{!matches!(fault,"validator"|"unknown-named"|"warm")}
fn eof(fault:&str)->bool{matches!(fault,"late-lf"|"late-decode"|"late-count"|"late-unstaged")}
#[derive(Clone,Copy)]struct Case{n:usize,route:&'static str,kind:&'static str,fault:&'static str,mixed:bool}
impl Case{
 fn unstaged(self)->bool{self.route.ends_with("unstaged")}
 fn prepared(self)->bool{self.kind=="prepared"}
 fn full(self)->bool{self.kind=="named-full"}
}
fn test_case(cs:Case){
 let record=records(cs.n,cs.mixed,cs.fault);
 let mut prev=None;let mut reports=Vec::new();
 for revised in [false,true] {
  meter::reset();empty_trace();F.set(cs.fault);STAGE.set((0,0,false));assert!(!FINAL.get() && !PREFIXING.get());CHANGED.set(revised);UNSTAGED.set(cs.unstaged());
  let docs:Arc<Mutex<BTreeMap<String,StorageMetadataDocument>>>=Default::default();
  let store=RemoteSessionStore::new(record.clone(),cs.route,cs.fault,docs.clone());
  let revision=store.test_revision();
  if cs.fault=="warm"{
   let setup=RemoteSessionStore::new(record.clone(),cs.route,"",docs);
   PreparedSession::from_dir(setup.service,PathBuf::from("/fixture/session")).unwrap().into_display_view(render_seed).unwrap();
   meter::reset();empty_trace();STAGE.set((0,0,false));
  }
  let named=if cs.kind=="unnamed-page"{None}else{Some(if cs.fault=="unknown-named"{"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}else{&revision})};
  let result:Result<(Vec<AppTranscriptMessage>,usize,Value)>=if cs.prepared(){
   PreparedSession::from_dir(store.service.clone(),PathBuf::from("/fixture/session"))
      .and_then(|prep|prep.into_display_view(render_seed))
      .map(|(_,v,cached)|{
       assert_eq!(v.summary.message_count,cs.n);assert_eq!(v.revision,record.len() as u64);assert_eq!(cached.is_some(),cs.fault=="warm");
       let full=matches!(cs.fault,"page"|"named-write");
       assert_eq!(v.cursor.is_none(),full);
       let start=if full{0}else{cs.n.saturating_sub(50)};
       let model=if let Some(c)=&v.cursor{assert_eq!(c.before,start);assert_eq!(c.revision,revision);json!([v.summary,v.revision,v.usage,c])}else{json!([v.summary,v.revision,v.usage])};
       (v.transcript,start,model)
      })
  }else if cs.full(){read::transcript_at_revision(&store,named.unwrap()).map(|r|(r,0,Value::Null))}
  else{
   read::transcript_page(&store,None,named).map(|p|{assert_eq!(p.revision,revision);assert_eq!(p.total,cs.n);assert!(p.base.is_none());let start=cs.n.saturating_sub(50);assert_eq!(p.start,start);assert_eq!(p.messages.len(),p.messages.capacity());(p.messages,start,Value::Null)})
  };
  let metrics=meter::take();
  let scan=STAGE.get();let events=get_trace();
  let find=|prefix:&str|events.iter().position(|s|s.starts_with(prefix));
  let count=|e:&str|events.iter().filter(|s|s.as_str()==e).count();
  let rendered=expect_render(cs.fault);let completed_scan=rendered && !eof(cs.fault);
  assert_eq!(count("Render"),usize::from(rendered),"n={} route={} kind={} fault={} result={result:?} trace={events:?}",cs.n,cs.route,cs.kind,cs.fault);
  assert_eq!(count("Digest"),usize::from(completed_scan));
  assert_eq!(metrics.is_null(),!rendered);
  if rendered && !cs.unstaged(){assert_eq!(scan.0,record.len());assert!(if cs.n>0{scan.1>100}else{scan.1==0});assert_eq!(scan.2,cs.fault!="reset");}
  else{assert_eq!(scan,(0,0,false));}
  if cs.prepared(){assert_eq!(events[0],"OpenSession");}
  if cs.fault=="warm"{assert!(find("WriteCache").is_none() && count("OpenDisplaySnapshot")==0);}
  let page_write=find("WriteCache display-data-");let prefix_write=find("WriteCache display-view-v1-prefix");
  let named_write=find("WriteCache display-revision-");let head_write=find("WriteCache display-view-v1-head");
  if !completed_scan{assert!(page_write.is_none() && prefix_write.is_none() && named_write.is_none() && head_write.is_none());}
  else {
   let dig=find("Digest").unwrap();assert!(events[dig+1..].iter().any(|e|e=="ReleaseSnapshot"));
   if cs.fault=="page"{assert!(page_write.is_some() && prefix_write.is_none() && named_write.is_none() && head_write.is_none());}
   else {
    assert!(dig<prefix_write.unwrap() && prefix_write.unwrap()<named_write.unwrap());
    if cs.n>0{assert!(page_write.unwrap()<prefix_write.unwrap());}
    if cs.fault=="named-write"{assert!(head_write.is_none());}else{assert!(named_write.unwrap()<head_write.unwrap());}
   }
  }
  if !cs.prepared() && completed_scan{assert_eq!(events[events.len()-2..],["FinalOpen","FinalRelease"]);}else{assert!(find("FinalOpen").is_none());}
  let (image,len,cap) = match result {
    Ok((rows,start,model))=>{
     assert!(get_error(cs.fault).is_none());assert_eq!(rows.len(),cs.n-start);verify_rows(&rows,&canonical(&record),start);
     (sha(&bytes(&(start,model,&rows))),rows.len(),rows.capacity())
    },
    Err(e)=>{
     let expected=get_error(cs.fault).unwrap_or_else(||panic!("unexpected {e:#}"));
     assert!(format!("{e:#}").contains(expected),"{}: got {e:#}",cs.fault);
     (format!("{e:#}"),0,0)
    }
  };
  let (header,head)=store.observed_headers_fixture(&revision);
  let expect_named=cs.fault=="warm" || (completed_scan&&!matches!(cs.fault,"page"|"named-write"));
  let expect_head=expect_named && cs.fault!="head";
  assert_eq!((header.is_some(),head.is_some()),(expect_named,expect_head));
  for h in [&header,&head].into_iter().flatten(){assert_eq!(h["prefix"].is_null(),cs.fault=="prefix");}
  let page_hashes: BTreeMap<_,_>=store.docs.lock().unwrap().iter().filter(|(k,_)|k.starts_with("display-data-")).map(|(key,doc)|{
   assert_eq!(key.strip_prefix("display-data-"),Some(doc.etag.as_str()));assert_eq!(storage_value_etag(&doc.value).unwrap(),doc.etag);
   (key.clone(),sha(&bytes(&doc.value)))
  }).collect();
  let eq=(image,len,cap,scan,events,sha(&bytes(&(header,head))),sha(&bytes(&page_hashes)),page_hashes.len());
  if let Some(old)=&prev{assert_eq!(old,&eq,"arm parity on {} {} {} {}",cs.n,cs.route,cs.kind,cs.fault);}else{prev=Some(eq);}
  reports.push(metrics);
 }
 let (out,len,cap,scan,trace,headers,pages,n_docs)=prev.unwrap();
 println!("{}",json!({"n":cs.n,"route":cs.route,"kind":cs.kind,"fault":cs.fault,"mixed":cs.mixed,"result":out,"result_rows":len,"result_capacity":cap,"stage":{"records":scan.0,"file_bytes":scan.1,"causal":scan.2},"headers_sha256":headers,"pages_sha256":pages,"page_docs":n_docs,"trace_count":trace.len(),"trace_sha256":sha(&bytes(&trace)),"trace_first_last":[trace.iter().take(10).collect::<Vec<_>>(),trace.iter().rev().take(12).rev().collect::<Vec<_>>()],"meters":{"stock":reports.remove(0),"candidate":reports.remove(0)}}));
}
fn render_seed(s:&mut RemoteJournalSnapshot)->Result<Vec<AppTranscriptMessage>>{render::journal_transcript_from_source(s,None)}
fn suffix_test(){
 use core::session_store::remote::view::PrefixIdentities;
 let mut a=PrefixIdentities::default();let mut b=PrefixIdentities::default();
 let mut rec=history_record(seed(3,4),1,false,false);let turn=Uuid::from_u128(77);rec.turn_id=Some(turn);
 assert!(a.visit(&rec,false) && b.visit_candidate(&rec,false));
 let baseline=a.messages.clone();
 // A same-turn record with fresh IDs still evaluates the other identities
 // without growing any set when the turn already makes the suffix dependent.
 let mut fresh=history_record(seed(3,4),2,false,false);fresh.turn_id=Some(turn);
 assert!(!a.visit(&fresh,true) && !b.visit_candidate(&fresh,true));
 fresh.turn_id=Some(Uuid::from_u128(78));assert!(a.visit(&fresh,true) && b.visit_candidate(&fresh,true));
 assert_eq!(a.messages,baseline);assert_eq!(a.messages,b.messages);assert_eq!(a.parts,b.parts);assert_eq!(a.calls,b.calls);
 let msg=seed(1,4).pop().unwrap();
 fresh.entry=JournalEntry::ModelMessageRecorded(ModelMessageRecorded{exchange_id:Uuid::from_u128(56),message:msg.clone()});
 assert!(a.visit(&fresh,false) && b.visit_candidate(&fresh,false));assert!(a.messages.contains(&msg.id));
 assert_eq!(a.messages,b.messages);assert_eq!(a.parts,b.parts);assert_eq!(a.exchanges,b.exchanges);
 println!("{}",json!({"n":0,"route":"suffix","kind":"identity","fault":"ok","passed":true,"meters":{"stock":null,"candidate":null}}));
}
fn main(){
 let mode=std::env::args().nth(1).expect("projected, fallback, unstaged or controls");
 if mode!="controls"{
  let route=match mode.as_str(){"projected"=>"projected","fallback"=>"fallback","unstaged"=>"unstaged",_=>panic!("invalid mode")};
  for n in [5000,50000]{test_case(Case{n,route,kind:"prepared",fault:"ok",mixed:false});}
  return;
 }
 for route in ["projected","fallback","unstaged","projected-unstaged"]{
  for (fault,n) in [("ok",0),("ok",1),("ok",63),("many-single",70),("reset",63),("warm",63),("validator",63)]{
   test_case(Case{n,route,kind:"prepared",fault,mixed:n>=63});
  }
 }
 for route in ["projected","fallback"]{
  for fault in ["late-lf","late-count","late-decode","page","prefix","named-write","head"] {
   test_case(Case{n:63,route,kind:"prepared",fault,mixed:true});
  }
  for (kind,fault) in [("unnamed-page","ok"),("named-full","ok"),("named-full","unknown-named"),("unnamed-page","final-hash")]{
   test_case(Case{n:63,route,kind,fault,mixed:true});
  }
 }
 for route in ["unstaged","projected-unstaged"]{
  test_case(Case{n:63,route,kind:"prepared",fault:"late-unstaged",mixed:true});
 }
 suffix_test();
 core::session_store::remote::view::semantic_test();
}
