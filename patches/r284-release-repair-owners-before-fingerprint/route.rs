#![allow(dead_code,unused_imports,unreachable_patterns)]
use anyhow::{Result,bail,ensure};use serde::{Serialize,Deserialize};use serde_json::{Value,json};
use std::{cell::{Cell,RefCell},collections::{BTreeMap,HashMap,HashSet},path::{Path,PathBuf},sync::{Arc,Mutex,atomic::{AtomicBool,Ordering}}};
use uuid::Uuid;
pub use proteus_contracts::{contracts,domain,model_standard};
use proteus_contracts::{app_protocol::*,contracts::*,domain::*,model_standard::*,storage::journal::*};
use proteus_contracts::contracts::{SessionStorageRequest as Request,SessionStorageResponse as Response};
mod core;mod snap;use snap::{RemoteJournalCursor,RemoteJournalSnapshot,RemoteValidatedRead};type JournalReadSnapshot=RemoteJournalSnapshot;
mod stage;use stage::{DisplayRecords,DisplayRecordWriter,is_display_kind};mod render;
mod stock;mod candidate;mod meter;
thread_local!{
 static EVENTS:RefCell<Vec<String>>=const{RefCell::new(Vec::new())};
 static FINAL:Cell<bool>=const{Cell::new(false)};
 static F:Cell<&'static str>=const{Cell::new("")};
 static STAGE:Cell<(usize,u64,bool)>=const{Cell::new((0,0,false))};
}
fn trace(s:String){EVENTS.with(|t|t.borrow_mut().push(s))}
fn fault_is(s:&str)->bool{F.get()==s}
fn ready_for_final(){assert!(!FINAL.replace(true));}
fn observe_render(s:&mut RemoteJournalSnapshot){
 assert_eq!(STAGE.get(),(0,0,false));
 STAGE.set(snap::stage_status(s));
 trace("Render".into());
 if fault_is("renderer"){snap::corrupt(s);}
}
fn bytes(v:&impl Serialize)->Vec<u8>{serde_json::to_vec(v).unwrap()}
fn sha(v:&[u8])->String{ring::digest::digest(&ring::digest::SHA256,v).as_ref().iter().map(|v|format!("{v:02x}")).collect()}
fn records(n:usize,mixed:bool,invalid:bool,context:bool)->Arc<Vec<JournalRecord>>{
 if n==0{return Arc::new(vec![])}
 let mut ms=seed(n,4);
 for (i,m) in ms.iter_mut().enumerate(){m.id=Uuid::from_u128(0x100000+i as u128);m.parts[0].part_id=Uuid::from_u128(0x200000+i as u128);assert!(m.metadata.is_null());if mixed&&i%5==0{m.metadata=json!({"ключ\n":[true,{},-0.25,"\0🦀\""]});}}
 let report=context.then(||{let mut r=HistoryCompactionReport::unchanged(n,Some("synthetic context compaction".into()));r.changed=true;r.output_messages=n;r});
 Arc::new(vec![JournalRecord{schema_version:JOURNAL_SCHEMA_VERSION,record_id:Uuid::from_u128(99),session_seq:1,timestamp_ms:1001,session_id:SESSION,execution_id:None,thread_id:Some(THREAD),turn_id:None,entry:JournalEntry::HistoryMutated(HistoryMutated{previous_revision:0,new_revision:if invalid{2}else{1},mutation:if context{HistoryMutationKind::Replace}else{HistoryMutationKind::Append},messages:ms,compaction:report,tool_results:vec![]})}])
}
fn primitive_rows(src:&[JournalRecord])->&[CanonicalMessage]{
 src.first().map(|r|match &r.entry { JournalEntry::HistoryMutated(h) => h.messages.as_slice(), _=>unreachable!() }).unwrap_or(&[])
}
fn verify_rows(rows:&[AppTranscriptMessage],source:&[CanonicalMessage],offset:usize){
 for (i,row) in rows.iter().enumerate(){
  let m=&source[offset+i];assert_eq!(row.message_id,Some(m.id));assert_eq!(row.timestamp_ms,Some(1001));
  assert_eq!(row.role,if (offset+i)%2==0{"user"}else{"assistant"});
  let ContentPart::Text{text}= &m.parts[0].payload else{unreachable!()};
  assert_eq!(&row.text,text);assert!(!row.streaming && row.images.is_empty() && row.tool.is_none());
 }
}
fn get_trace()->Vec<String>{EVENTS.with(|e|e.borrow().clone())}
fn empty_trace(){EVENTS.with(|t|t.borrow_mut().clear());}
fn get_error(fault:&str)->Option<&'static str>{
 Some(match fault{
 "final-hash"|"final-revision"|"named-race"|"invalid-final"=>"history source changed during recovery; refresh the session snapshot",
 "final-wrong-kind"=>"storage returned an unexpected snapshot response",
 "final-wrong-session"=>"storage snapshot belongs to another session",
 "final-transport"=>"fixture worker disconnected",
 "final-missing"=>"session no longer exists",
 "invalid-before"=>"history position is outside the requested revision",
 "unknown-named"=>"history revision changed; refresh the session snapshot",
 "validator"=>"history revision must increment",
 "renderer"|"late-prefix"=>"transcript staging record count changed",
 _=>return None
 })
}
fn expect_render(fault:&str)->bool{!matches!(fault,"validator"|"unknown-named"|"named-race"|"warm")}
fn expect_final(fault:&str)->bool{expect_render(fault) && !matches!(fault,"renderer"|"late-prefix")}
fn expect_final_release(fault:&str)->bool{expect_final(fault)&&!matches!(fault,"final-transport"|"final-missing"|"final-wrong-kind"|"final-wrong-session")}
fn cache_fault(fault:&'static str)->&'static str{match fault{"invalid-final"=>"final-hash",x=>x}}
#[derive(Clone,Copy)]struct Case{n:usize,route:&'static str,kind:&'static str,fault:&'static str,before:Option<usize>,mixed:bool}
impl Case{
 fn named(self)->bool{self.kind!="unnamed-page"}
 fn full(self)->bool{self.kind=="named-full"}
}
fn test_case(cs:Case){
 let record=records(cs.n,cs.mixed,cs.fault=="validator",cs.fault=="context");
 let mut prev=None;let mut reports=Vec::new();
 for revised in [false,true] {
  meter::reset();empty_trace();F.set(cs.fault);STAGE.set((0,0,false));assert!(!FINAL.get());
  let docs:Arc<Mutex<BTreeMap<String,StorageMetadataDocument>>>=Default::default();
  let store=RemoteSessionStore::new(record.clone(),cs.route,cache_fault(cs.fault),docs.clone());
  let revision=store.test_revision();
  if cs.fault=="warm"{
   let setup=RemoteSessionStore::new(record.clone(),cs.route,"",docs);
   stock::transcript_page(&setup,None,None).unwrap();
   meter::reset();empty_trace();STAGE.set((0,0,false));
  }
  let named=if cs.named(){Some(if cs.fault=="unknown-named"{"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}else{&revision})}else{None};
  let page=if revised{candidate::transcript_page}else{stock::transcript_page};
  let all=if revised{candidate::transcript_at_revision}else{stock::transcript_at_revision};
  let result=if cs.full(){all(&store,named.unwrap()).map(|r|(0,r.len(),r,None))}else{
   page(&store,cs.before,named).map(|p|{assert_eq!(p.revision,revision);(p.start,p.total,p.messages,p.base)})
  };
  let metrics=meter::take();
  if cs.fault=="context"{assert_eq!(metrics["shape"]["context"],1);}
  let scan=STAGE.get();let events=get_trace();
  let find=|prefix:&str|events.iter().position(|s|s.starts_with(prefix));
  let count=|e:&str|events.iter().filter(|s|s.as_str()==e).count();
  assert_eq!(count("Render"),usize::from(expect_render(cs.fault)));
  assert_eq!(count("FinalOpen"),usize::from(expect_final(cs.fault)));
  assert_eq!(count("FinalRelease"),usize::from(expect_final_release(cs.fault)));
  if let Some(i)=find("FinalOpen"){
   assert!(find("Render").unwrap()<i);
   assert!(events[..i].iter().any(|x|x=="ReleaseSnapshot"));
   assert!(events[..i].iter().any(|x|x.starts_with("ReadCache display-view-v1-head")));
   assert!(!events[i+1..].iter().any(|x|x.starts_with("WriteCache")));
   if expect_final_release(cs.fault){assert_eq!(events.get(i+1).unwrap(),"FinalRelease");}
  }
  if expect_render(cs.fault) {
   assert_eq!(scan.0,usize::from(cs.n>0));assert!(if cs.n>0{scan.1>100}else{scan.1==0});
   assert_eq!(count("ReadRecords 0"),usize::from(cs.route!="projected"));assert_eq!(count("ReadDisplayRecords 0"),usize::from(cs.route=="projected"));
   assert!(scan.2);
  }
  if cs.fault=="warm"{
   assert!(scan.0==0 && find("WriteCache").is_none() && count("OpenDisplaySnapshot")==0);
   assert_eq!(count("OpenSnapshot"),usize::from(!cs.named()));
  }else if cs.named() {
   assert_eq!(events[1],"OpenSnapshot");assert_eq!(events[2],"ReleaseSnapshot");
  }
  let page_write=find("WriteCache display-data-");let prefix_write=find("WriteCache display-view-v1-prefix");
  let named_write=find("WriteCache display-revision-");let head_write=find("WriteCache display-view-v1-head");
  if !expect_final(cs.fault){assert!(page_write.is_none() && prefix_write.is_none() && named_write.is_none() && head_write.is_none());}
  else if cs.fault=="page"{assert!(page_write.is_some() && prefix_write.is_none() && named_write.is_none() && head_write.is_none());}
  else {
   assert!(prefix_write.unwrap()<named_write.unwrap()); if cs.n>0{assert!(page_write.unwrap()<prefix_write.unwrap());}
   if cs.fault=="named-write"{assert!(head_write.is_none());}else{assert!(named_write.unwrap()<head_write.unwrap());}
  }
  let (image,cap) = match result {
    Ok((start,total,rows,base))=>{
     assert!(get_error(cs.fault).is_none());assert_eq!(total,cs.n);assert!(base.is_none());
     let end=cs.before.unwrap_or(total);assert_eq!(start,if cs.full(){0}else{end.saturating_sub(50)});
     assert_eq!(rows.len(),end-start);verify_rows(&rows,primitive_rows(&record),start);
     if !cs.full()&&cs.fault!="warm"{assert_eq!(rows.capacity(),rows.len());}
     (sha(&bytes(&(start,total,rows,base))),end-start)
    },
    Err(e)=>{
     let expected=get_error(cs.fault).unwrap_or_else(||panic!("unexpected {e:#}"));
     assert!(format!("{e:#}").contains(expected),"{}: got {e:#}",cs.fault);
     if cs.fault=="final-missing"{assert_eq!(e.downcast_ref::<SessionStorageFailure>(),Some(&SessionStorageFailure::MissingSession));}
     (format!("{e:#}"),0)
    }
  };
  let (header,head)=store.observed_headers_fixture(&revision);
  let expect_named=cs.fault=="warm" || (expect_final(cs.fault)&&!matches!(cs.fault,"page"|"named-write"));
  let expect_head=expect_named && cs.fault!="head";
  assert_eq!((header.is_some(),head.is_some()),(expect_named,expect_head));
  for h in [&header,&head].into_iter().flatten(){assert_eq!(h["prefix"].is_null(),cs.fault=="prefix");}
  let page_hashes: BTreeMap<_,_>=store.docs.lock().unwrap().iter().filter(|(k,_)|k.starts_with("display-data-")).map(|(key,doc)|{
   assert_eq!(key.strip_prefix("display-data-"),Some(doc.etag.as_str()));assert_eq!(storage_value_etag(&doc.value).unwrap(),doc.etag);
   (key.clone(),sha(&bytes(&doc.value)))
  }).collect();
  let eq=(image,cap,scan,events,sha(&bytes(&(header,head))),sha(&bytes(&page_hashes)),page_hashes.len());
  if let Some(old)=&prev{assert_eq!(old,&eq,"arm parity on {} {} {} {}",cs.n,cs.route,cs.kind,cs.fault);}else{prev=Some(eq);}
  reports.push(metrics);
 }
 let (out,cap,scan,trace,headers,pages,n_docs)=prev.unwrap();
 println!("{}",json!({"n":cs.n,"route":cs.route,"kind":cs.kind,"fault":cs.fault,"mixed":cs.mixed,"before":cs.before,"result":out,"result_rows":cap,"stage":{"records":scan.0,"file_bytes":scan.1,"causal":scan.2},"headers_sha256":headers,"pages_sha256":pages,"page_docs":n_docs,"trace_count":trace.len(),"trace_sha256":sha(&bytes(&trace)),"trace_first_last":[trace.iter().take(10).collect::<Vec<_>>(),trace.iter().rev().take(12).rev().collect::<Vec<_>>()],"meters":{"stock":reports.remove(0),"candidate":reports.remove(0)}}));
}
fn main(){
 let mode=std::env::args().nth(1).expect("projected, fallback, or controls");
 if mode!="controls"{
  let route=match mode.as_str(){"projected"=>"projected","fallback"=>"fallback",_=>panic!("invalid mode")};
  for n in [5000,50000]{for kind in ["unnamed-page","named-page","named-full"]{test_case(Case{n,route,kind,fault:"ok",before:None,mixed:false});}}
  return;
 }
 for route in ["projected","fallback","unsupported"]{
  for kind in ["unnamed-page","named-page","named-full"]{
   for (fault,n,before) in [("ok",0,None),("ok",1,Some(0)),("ok",63,None),("warm",63,None),("final-new-handle",63,None)]{
    if kind=="named-full"&&before.is_some(){continue;}
    test_case(Case{n,route,kind,fault,before,mixed:n==63});
   }
  }
 }
 for route in ["projected","fallback"]{
  for (fault,kind,n,before) in [
   ("context","named-page",63,None),("unknown-named","named-page",63,None),("named-race","named-page",63,None),("validator","unnamed-page",63,None),
   ("renderer","unnamed-page",63,None),("late-prefix","named-full",63,None),
   ("page","unnamed-page",63,None),("prefix","unnamed-page",63,None),("named-write","unnamed-page",63,None),("head","unnamed-page",63,None),
   ("final-wrong-kind","unnamed-page",63,None),("final-wrong-session","named-page",63,None),("final-hash","unnamed-page",63,None),
   ("final-revision","unnamed-page",63,None),("final-missing","named-full",63,None),("final-transport","unnamed-page",63,None),
   ("final-release","named-page",63,None),("invalid-before","unnamed-page",63,Some(64)),("invalid-final","unnamed-page",63,Some(64))
  ]{test_case(Case{n,route,kind,fault,before,mixed:true});}
 }
}
