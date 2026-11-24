#![allow(dead_code,unused_imports,unreachable_patterns)]
use anyhow::{Result,bail,ensure};use serde::{Serialize,Deserialize};use serde_json::{Value,json};
use std::{cell::{Cell,RefCell},collections::{BTreeMap,HashMap,HashSet},path::{Path,PathBuf},sync::{Arc,Mutex,atomic::{AtomicUsize,Ordering}}};
use uuid::Uuid;
pub use proteus_contracts::{contracts,domain,model_standard};
use proteus_contracts::{app_protocol::*,contracts::*,domain::*,model_standard::*,storage::journal::*};
use proteus_contracts::contracts::{SessionStorageRequest as Request,SessionStorageResponse as Response};
mod core;mod snap;use snap::{RemoteJournalCursor,RemoteJournalSnapshot,RemoteValidatedRead};type JournalReadSnapshot=RemoteJournalSnapshot;
mod stage;use stage::{DisplayRecords,DisplayRecordWriter,is_display_kind};mod render;mod read;mod http_stock;mod http_candidate;mod meter;
use core::session_store::remote::view::RemoteCacheSource;
thread_local!{
 static EVENTS:RefCell<Vec<String>>=const{RefCell::new(Vec::new())};
 static FINAL:Cell<bool>=const{Cell::new(false)};
 static CHANGED:Cell<bool>=const{Cell::new(false)};
 static DECODE:Cell<[[usize;3];3]>=const{Cell::new([[0;3];3])};
 static STAGE:Cell<(usize,u64,bool)>=const{Cell::new((0,0,false))};
 static READ_FAULT:RefCell<Option<String>>=const{RefCell::new(None)};
}
fn decode_mark<T:'static>(slot:usize){
 let t=std::any::TypeId::of::<T>();
 let i=if t==std::any::TypeId::of::<CanonicalMessage>(){0}else if t==std::any::TypeId::of::<ModelContextObservation>(){1}
 else if t==std::any::TypeId::of::<AppTranscriptMessage>(){2}else{return};
 let mut m=DECODE.get();m[i][slot]+=1;DECODE.set(m);
}
fn trace(s:String){EVENTS.with(|t|t.borrow_mut().push(s))}
fn at_final_recheck(s:&RemoteSessionStore)->Option<RemoteCacheSource>{meter::final_recheck();assert!(!FINAL.replace(true));RemoteCacheSource::read(s)}
fn observe_render(s:&mut RemoteJournalSnapshot){STAGE.set(snap::stage_status(s));trace("Render".into());}
fn render_seed(s:&mut RemoteJournalSnapshot)->Result<Vec<AppTranscriptMessage>>{render::journal_transcript_from_source(s,None)}
fn bytes(v:&impl Serialize)->Vec<u8>{serde_json::to_vec(v).unwrap()}
fn sha(v:&[u8])->String{ring::digest::digest(&ring::digest::SHA256,v).as_ref().iter().map(|v|format!("{v:02x}")).collect()}
fn records(n:usize,context:bool,invalid:bool)->Arc<Vec<JournalRecord>>{
 if n==0{return Arc::new(vec![])}
 let mut ms=seed(n,4);
 for (i,m) in ms.iter_mut().enumerate(){m.id=Uuid::from_u128(0x100000+i as u128);m.parts[0].part_id=Uuid::from_u128(0x200000+i as u128);}
 let report=context.then(||{let mut r=HistoryCompactionReport::unchanged(n,Some("synthetic context compaction".into()));r.changed=true;r});
 Arc::new(vec![JournalRecord{schema_version:JOURNAL_SCHEMA_VERSION,record_id:Uuid::from_u128(99),session_seq:1,timestamp_ms:1001,session_id:SESSION,execution_id:None,thread_id:Some(THREAD),turn_id:None,entry:JournalEntry::HistoryMutated(HistoryMutated{previous_revision:0,new_revision:if invalid{2}else{1},mutation:if context{HistoryMutationKind::Replace}else{HistoryMutationKind::Append},messages:ms,compaction:report,tool_results:vec![]})}])
}
fn expected_context(k:usize)->Vec<ModelContextObservation>{
 match k{
  0=>vec![],1=>vec![ModelContextObservation::HistoryCompacted],
  _=>(0..k).map(|i| match i%3{
    0=>ModelContextObservation::HistoryCompacted,
    1=>ModelContextObservation::ContextWindowExceeded{max_input_tokens:4096+i as u32},
    _=>ModelContextObservation::Usage{total_tokens:i as u64*64,last_tokens:i as u32}
  }).collect()
 }
}
fn canonical(src:&[JournalRecord])->&[CanonicalMessage]{
 src.first().map(|r|match &r.entry{JournalEntry::HistoryMutated(x)=>x.messages.as_slice(),_=>unreachable!()}).unwrap_or(&[])
}
fn verify_rows(rows:&[AppTranscriptMessage],src:&[CanonicalMessage],offset:usize){
 for (i,row) in rows.iter().enumerate(){
  let m=&src[offset+i];assert_eq!(row.message_id,Some(m.id));assert_eq!(row.timestamp_ms,Some(1001));
  assert_eq!(row.role,if (i+offset)%2==0{"user"}else{"assistant"});
  let ContentPart::Text{text}= &m.parts[0].payload else{unreachable!()};
  assert_eq!(&row.text,text);assert!(!row.streaming && row.images.is_empty() && row.tool.is_none());
 }
}
fn empty_trace(){EVENTS.with(|e|e.borrow_mut().clear());}
#[derive(Clone,Copy)]struct Case{n:usize,route:&'static str,kind:&'static str,fault:&'static str,ctx:usize,target:Option<(&'static str,bool,&'static str)>}
fn run_case(cs:Case){
 let cold=cs.fault.starts_with("cold-");
 let bad=cs.fault=="cold-invalid"||cs.fault=="typed-then-invalid";
 let src=records(cs.n,cs.ctx>0,bad);
 let seed_src=records(cs.n,cs.ctx>0,false);
 let warm=!cold && (cs.fault=="ok"||matches!(cs.fault,"initial-release"|"final-release"|"final-new-handle"));
 let mut prev=None;let mut metrics=Vec::new();
 for changed in [false,true]{
  CHANGED.set(changed);meter::reset();READ_FAULT.with(|f|*f.borrow_mut()=None);STAGE.set((0,0,false));assert!(!FINAL.get());
  let docs:Arc<Mutex<BTreeMap<String,StorageMetadataDocument>>>=Default::default();
  let setup=RemoteSessionStore::new(seed_src.clone(),cs.route,"",docs.clone());
  let mut caches=json!(null);let target=if !cold{
   setup.prepare_warm(cs.ctx).unwrap();
   let h=setup.warm_header();
   assert_eq!(h["conversation"]["rows"],cs.n);assert_eq!(h["transcript"]["rows"],cs.n);assert_eq!(h["context"]["rows"],cs.ctx);
   caches=json!({
    "sections": (["conversation","context","transcript"].iter().map(|name| {
     let s=&h[*name];json!({"section":name,"rows":s["rows"],"pages":s["pages"].as_array().unwrap().len(),"packs":s["packs"].as_array().map_or(0,Vec::len)})
    }).collect::<Vec<_>>()),"seed_stage_file_bytes":STAGE.get().1
   });
   if cs.n>=5000{assert_eq!(STAGE.get().0,1);assert!(STAGE.get().1>cs.n as u64*400);}
   if let Some((sect,late,how))=cs.target{
    let (key,packed)=setup.damage(sect,late,how);
    if matches!(how,"storage-wrong-kind"|"storage-failure"){READ_FAULT.with(|f|*f.borrow_mut()=Some(key.clone()));}
    json!({"key":key,"section":sect,"late":late,"method":how,"packed":packed})
   }else{
    if matches!(cs.fault,"invalid-head"|"false-head"|"count-head"){setup.alter_head(cs.fault);}
    json!(null)
   }
  }else{json!(null)};
  empty_trace();STAGE.set((0,0,false));DECODE.set([[0;3];3]);meter::reset();
  let real_fault=match cs.fault{"cold-page"=>"page","cold-named"=>"named-write",x=>x};
  let store=RemoteSessionStore::new(src.clone(),cs.route,real_fault,docs);
  let result:Result<(Vec<AppTranscriptMessage>,Value)>=match cs.kind{
   "full-model"=>read::current_read_model(&store).map(|m|{
    assert_eq!(m.conversation.messages,canonical(&src) );
    assert_eq!(m.conversation.model_context,expected_context(cs.ctx));
    assert!(m.prefix.is_none());
    let extra=json!([m.summary,m.conversation,m.usage]);(m.transcript,extra)
   }),
   "named"=>read::transcript_at_revision(&store,&store.test_revision()).map(|r|(r,Value::Null)),
   "page"=>read::transcript_page(&store,None,None).map(|p|{
    assert_eq!(p.total,cs.n);assert_eq!(p.start,cs.n.saturating_sub(50));(p.messages,Value::Null)
   }),
   _=>{
    let f=if changed{http_candidate::restore}else{http_stock::restore};
    f(store.service.clone(),PathBuf::from("/fixture/session")).map(|r|(r,Value::Null))
   }
  };
  let measure=meter::take();assert!(!FINAL.get());
  let trace=EVENTS.with(|e|e.borrow().clone());
  let ctr=|k:&str|trace.iter().filter(|e|e.as_str()==k).count();
  let damaged=cs.target.is_some();
  let render_expected=!warm && !bad;
  assert_eq!(ctr("Render"),usize::from(render_expected),"{} {} {} {:?}",cs.n,cs.route,cs.fault,result);
  if cs.kind=="history"{assert_eq!(trace[0],"OpenSession");}
  if warm{
   assert_eq!((ctr("OpenSnapshot"),ctr("FinalOpen"),ctr("FinalRelease")),
     if cs.kind=="named"{(0,0,0)}else if cs.kind=="page"{(1,0,0)}else{(1,1,1)});
   assert!(!trace.iter().any(|e|e.starts_with("WriteCache")));
   assert_eq!(ctr("OpenDisplaySnapshot"),0);assert_eq!(STAGE.get(),(0,0,false));
  }else if render_expected{
   assert_eq!(ctr("OpenDisplaySnapshot"),1);
  }
  if damaged{
   assert_eq!(ctr("FinalOpen"),0,"{target:?}");
   if let Some((section,_,how))=cs.target{
    let i=match section{"conversation"=>0,"context"=>1,_=>2};
    let m=DECODE.get()[i];
    if how=="type"{assert_eq!(m[0],m[1]+1,"type-invalid leaf never reached typed serde: {target:?} {m:?}");assert_eq!(m[2],0);}
    if how=="count"{assert_eq!(m[0],m[1]+1);assert_eq!(m[2],1,"valid typed wrong-count leaf must reach cardinality guard: {target:?}");}
   }
  }
  if cs.fault.starts_with("initial-") && cs.fault!="initial-release"{assert_eq!(ctr("FinalOpen"),0);}
  if let Some(i)=trace.iter().position(|s|s=="FinalOpen"){
   let want_release=!matches!(cs.fault,"final-wrong-kind"|"final-wrong-session"|"final-transport"|"final-missing");
   assert_eq!(trace.get(i+1).is_some_and(|s|s=="FinalRelease"),want_release);
  }
  let (out,returned,cap)=match result{
   Ok((rows,extra))=>{
    assert!(!bad);let start=if cs.kind=="page"{cs.n.saturating_sub(50)}else{0};
    assert_eq!(rows.len(),cs.n-start);verify_rows(&rows,canonical(&src),start);
    (sha(&bytes(&(extra,&rows))),rows.len(),rows.capacity())
   },
   Err(e)=>{assert!(bad,"{}: {e:#}",cs.fault);assert!(format!("{e:#}").contains("history revision must increment"));(format!("{e:#}"),0,0)}
  };
  let (header,pages,n_docs)=store.cache_proof();
  let eq=(out,returned,cap,trace,STAGE.get(),sha(&bytes(&header)),pages,n_docs,caches,target,DECODE.get());
  if let Some(old)=&prev{assert_eq!(old,&eq,"parity for {} {} {} {}",cs.n,cs.route,cs.kind,cs.fault);}
  else{prev=Some(eq);}
  metrics.push(measure);
 }
 let (out,len,cap,trace,stage,head,pages,n_docs,caches,target,typed)=prev.unwrap();
 println!("{}",json!({"n":cs.n,"ctx":cs.ctx,"route":cs.route,"kind":cs.kind,"fault":cs.fault,"target":target,"typed_boundary":typed,"warm":warm,"result":out,"rows":len,"capacity":cap,"fallback_stage":{"records":stage.0,"bytes":stage.1,"causal":stage.2},"seed_cache":caches,"headers_sha256":head,"pages_sha256":pages,"page_docs":n_docs,"trace":trace,"meters":{"stock":metrics.remove(0),"candidate":metrics.remove(0)}}));
}
fn main(){
 let mode=std::env::args().nth(1).expect("projected, fallback, controls");
 if mode!="controls"{
  let route=match mode.as_str(){"projected"=>"projected","fallback"=>"fallback",_=>panic!("invalid mode")};
  for n in [5000,50000]{run_case(Case{n,route,kind:"history",fault:"ok",ctx:0,target:None});}
  return;
 }
 for route in ["projected","fallback"]{
  for (n,ctx) in [(0,0),(1,0),(49,1),(50,1),(51,1),(449,0),(450,0),(451,110)]{
   run_case(Case{n,route,kind:"history",fault:"ok",ctx,target:None});
  }
  for fault in ["cold-miss","cold-invalid","cold-page","cold-named","invalid-head","false-head","count-head",
   "initial-hash","initial-wrong-kind","initial-wrong-session","initial-missing","initial-release",
   "final-hash","final-revision","final-new-handle","final-wrong-kind","final-wrong-session","final-missing","final-transport","final-release"]{
   run_case(Case{n:63,route,kind:"history",fault,ctx:1,target:None});
  }
  for (section,ctx) in [("conversation",1),("context",110),("transcript",1)]{
   for late in [false,true]{
    for how in ["type","count","missing","wrong-hash"]{
     run_case(Case{n:451,route,kind:"history",fault:how,ctx,target:Some((section,late,how))});
    }
   }
  }
  for section in ["conversation","transcript"]{
   for how in ["deflate","packed-bytes","storage-wrong-kind","storage-failure"]{
    run_case(Case{n:451,route,kind:"history",fault:how,ctx:1,target:Some((section,false,how))});
   }
  }
  for (section,ctx) in [("conversation",1),("context",110)]{run_case(Case{n:451,route,kind:"history",fault:"singleton-bytes",ctx,target:Some((section,true,"singleton-bytes"))});}
  run_case(Case{n:451,route,kind:"history",fault:"typed-then-invalid",ctx:1,target:Some(("conversation",true,"type"))});
  for kind in ["full-model","named","page"]{
   run_case(Case{n:451,route,kind,fault:"ok",ctx:110,target:None});
  }
 }
}
