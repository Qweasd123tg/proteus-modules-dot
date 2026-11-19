use super::*;
use crate::app_server::transcript::plain_pages::{PlainPages, Proof};
use std::{fs::File, io::{BufRead,BufReader,BufWriter,Write,Seek}, time::Instant};
use anyhow::{Result,ensure};

struct Staged { file: File, spans: usize, proof: Option<Proof> }
struct Count<W> { out: W, pos: u64 }
impl<W: Write> Write for Count<W> {
 fn write(&mut self, b: &[u8])->std::io::Result<usize>{let n=self.out.write(b)?;self.pos+=n as u64;Ok(n)}
 fn flush(&mut self)->std::io::Result<()>{self.out.flush()}
}
fn stage(projection:&JournalProjection, candidate:bool)->Result<Staged>{
 let mut data = Count{out:BufWriter::new(tempfile::tempfile()?),pos:0};
 let mut proof=if candidate {Proof::new(None)?}else{None};
 let mut spans=0;
 // Real JournalProjection::build completed before publishing a stage.
 for r in &projection.records {
   if !crate::core::is_display_kind(r.entry.kind()) {continue}
   let pos=data.pos;
   serde_json::to_writer(&mut data,r)?;
   data.write_all(b"\n")?;
   if let Some(p)=&mut proof && !p.observe(r,pos,data.pos-pos)? {proof=None;}
   spans+=1;
 }
 let file=data.out.into_inner()?;
 Ok(Staged{file,spans,proof})
}
fn replay(mut s:Staged)->Result<Vec<AppTranscriptMessage>>{
 super::super::source::transcript_from_scan(|v|{
    s.file.rewind()?;
    let mut file=BufReader::new(&mut s.file);
    let mut line=Vec::new();
    let mut n=0;
    while file.read_until(b'\n',&mut line)?>0 {
       ensure!(line.ends_with(b"\n"),"truncated staged row");
       v(serde_json::from_slice(&line)?)?;line.clear();n+=1;
    }
    ensure!(n==s.spans,"incomplete staged snapshot");Ok(())
 },None)
}
fn archive(rows:usize,batch:usize, blanks:bool, compact:bool)->JournalProjection{
 let sid=new_session_id(); let tid=new_thread_id();
 let mut records=Vec::new();
 let messages=(0..rows).map(|i|{
   let mut m=CanonicalMessage::text(if i%2==0 {MessageRole::User}else{MessageRole::Assistant},if blanks&&i%7==0 {"  \n".to_owned()}else{format!("{i} {}", "Фиктивная строка журнала. ".repeat(3))});
   if i%2==1 {m.phase=Some(crate::model_standard::MessagePhase::FinalAnswer)}
   m
 }).collect::<Vec<_>>();
 for chunk in messages.chunks(batch){
  let seq=records.len() as u64+1;
  records.push(JournalRecord{schema_version:JOURNAL_SCHEMA_VERSION,record_id:new_record_id(),session_seq:seq,session_id:sid,execution_id:None,thread_id:Some(tid),turn_id:None,timestamp_ms:42-seq as i64,
    entry:JournalEntry::HistoryMutated(HistoryMutated{previous_revision:seq-1,new_revision:seq,mutation:HistoryMutationKind::Append,messages:chunk.to_vec(),compaction:None,tool_results:vec![]})});
 }
 if compact {
   let last=records.last().unwrap().clone();
   let mut comp=crate::domain::HistoryCompactionReport::unchanged(rows,None);comp.changed=true;
   let seq=last.session_seq+1;
   records.push(JournalRecord {record_id:new_record_id(),session_seq:seq,entry:JournalEntry::HistoryMutated(HistoryMutated{
       previous_revision:seq-1,new_revision:seq,mutation:HistoryMutationKind::Replace,messages:messages[rows.saturating_sub(100)..].to_vec(),
       compaction:Some(comp),tool_results:vec![]}),..last});
 }
 JournalProjection::build(sid,records).unwrap()
}
fn mixed_turn(t: usize, session_id: crate::domain::SessionId, thread_id: ThreadId) -> Vec<JournalRecord> {


    let turn_id = new_turn_id();
    let execution_id = new_execution_id();
    let exchange_id = new_exchange_id();
    let user = CanonicalMessage::text(MessageRole::User, "inspect");
    let call = ToolCall::new(format!("call-{t}"), "shell", json!({"command": "ls"}));
    let response_message = CanonicalMessage::new(
        MessageRole::Assistant,
        vec![
            ContentPart::ReasoningSummary {
                text: "private summary".to_owned(),
            },
            ContentPart::Reasoning {
                text: "private reasoning".to_owned(),
                signature: Some("opaque signature".to_owned()),
            },
            ContentPart::Text {
                text: "checking".to_owned(),
            },
            ContentPart::ToolCall { call: call.clone() },
        ],
    );
    let response = CanonicalModelResponse::new(
        response_message.clone(),
        vec![call.clone()],
        FinishReason::ToolCalls,
    );
    let request = CanonicalModelRequest::new(ModelRef::new("fake", "model"), vec![user.clone()]);
    let result = ToolResult::ok(call.id.clone(), "listing");
    let mut records = vec![
        record(
            session_id,
            Some(execution_id),
            thread_id,
            turn_id,
            1,
            JournalEntry::TurnOpened(TurnOpened {
                intent: None,
                task: AgentTask::new("inspect", "/tmp/workspace".into()),
                base_history_revision: t as u64,
                module_epoch: 0,
                config_snapshot: json!({}),
            }),
        ),
        record(
            session_id,
            None,
            thread_id,
            turn_id,
            2,
            JournalEntry::HistoryMutated(HistoryMutated {
                previous_revision: t as u64,
                new_revision: t as u64 + 1,
                tool_results: Vec::new(),
                mutation: HistoryMutationKind::Append,
                messages: vec![user],
                compaction: None,
            }),
        ),
        record(
            session_id,
            Some(execution_id),
            thread_id,
            turn_id,
            3,
            JournalEntry::ModelRequestRecorded(ModelRequestRecorded {
                exchange_id,
                origin: ModelCallOrigin::Direct,
                owner: crate::contracts::OperationOwner::Workflow,
                request,
            }),
        ),
        record(
            session_id,
            Some(execution_id),
            thread_id,
            turn_id,
            4,
            JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
                exchange_id,
                outcome: ModelResponseOutcome::Response { response },
            }),
        ),
        record(
            session_id,
            Some(execution_id),
            thread_id,
            turn_id,
            5,
            JournalEntry::ToolCallRecorded(ToolCallRecorded {
                call: call.clone(),
                phase: ToolCallRecordPhase::Requested {
                    owner: crate::contracts::OperationOwner::Workflow,
                },
            }),
        ),
        record(
            session_id,
            Some(execution_id),
            thread_id,
            turn_id,
            6,
            JournalEntry::ToolCallRecorded(ToolCallRecorded {
                call,
                phase: ToolCallRecordPhase::Resolved {
                    resolution: ToolCallResolution::Allowed,
                },
            }),
        ),
        record(
            session_id,
            Some(execution_id),
            thread_id,
            turn_id,
            7,
            JournalEntry::ToolResultRecorded(ToolResultRecorded { result }),
        ),
        record(
            session_id,
            None,
            thread_id,
            turn_id,
            8,
            JournalEntry::TurnSettled(TurnSettled {
                status: TurnSettlementStatus::Error,
                output: None,
                error: Some("workflow failed after tool execution".to_owned()),
            }),
        ),
    ];
    records.insert(
        3,
        record(
            session_id,
            Some(execution_id),
            thread_id,
            turn_id,
            4,
            JournalEntry::ModelMessageRecorded(
                serde_json::from_value(json!({
                    "exchange_id": exchange_id, "message": response_message,
                }))
                .unwrap(),
            ),
        ),
    );
    for (index, item) in records.iter_mut().enumerate() {
        item.session_seq = (t * 9 + index + 1) as u64;
        item.timestamp_ms = item.session_seq as i64;
    }
records
}

#[test]
fn exact_pages_and_strict_guards(){
 let projection=archive(839,31,true,true);
 let reference=TranscriptReplay::new(&projection.records,0).render(projection.records.iter(),None);
 let s=stage(&projection,true).unwrap(); let mut p=s.proof.unwrap().seal(s.file).unwrap();
 assert_eq!(p.rows as usize,reference.len());
 for i in 0..=reference.len(){ for limit in [0,1,17,50]{
    let (page,reads,_) =p.page(i as u64,limit).unwrap();
    assert_eq!(serde_json::to_vec(&page).unwrap(),serde_json::to_vec(&reference[i.saturating_sub(limit)..i]).unwrap());
    assert!(reads as usize<=page.len());
 }}
 assert!(p.page(p.rows+1,50).is_err());
 assert!(p.page(p.rows,51).is_err());
 assert!(Proof::new(Some(new_turn_id())).unwrap().is_none());
 let one=archive(1,1,false,false);
 let mut proof=Proof::new(None).unwrap().unwrap();assert!(!proof.observe(&one.records[0],0,262145).unwrap());
 let mut proof=Proof::new(None).unwrap().unwrap();assert!(!proof.observe(&one.records[0],u64::MAX,10).unwrap());
 // Simulate a partial stage: no partial page ever returned, even at a valid cursor.
 let s=stage(&projection,true).unwrap(); s.file.set_len(16).unwrap();
 let mut p=s.proof.unwrap().seal(s.file).unwrap();assert!(p.page(p.rows,50).is_err());
 // A duplicate ID at the end of an append-only source is invalid, not a page.
 let mut records=archive(3,3,false,false).records;let sid=records[0].session_id;
 let mut bad=records[0].clone();bad.session_seq=2;bad.record_id=new_record_id();
 let JournalEntry::HistoryMutated(m)=&mut bad.entry else{unreachable!()};m.previous_revision=1;m.new_revision=2;
 records.push(bad);assert!(JournalProjection::build(sid,records).is_err());
}
#[test]
fn eligible_prefix_does_not_hide_late_facts(){
 let src=archive(820,100,false,true);
 let refrows=|r:&[JournalRecord]|TranscriptReplay::new(r,super::super::replay_start(r,None)).render(r.iter(),None);
 let last=src.records.last().unwrap().clone();let sid=last.session_id;
 let old=match &src.records[0].entry {JournalEntry::HistoryMutated(x)=>x.messages[0].clone(),_=>unreachable!()};
 // Compaction retains an old valid row *outside* our bounded positive witness.
 let mut recs=src.records.clone(); if let JournalEntry::HistoryMutated(m)=&mut recs.last_mut().unwrap().entry{m.messages.push(old.clone())}
 let p=JournalProjection::build(sid,recs).unwrap();assert!(stage(&p,true).unwrap().proof.is_none());
 // Reuse of inactive part *after* compaction: canonical append valid but it adds no row.
 let mut recs=src.records.clone(); let mut r=last.clone();r.session_seq+=1;r.record_id=new_record_id();
 let JournalEntry::HistoryMutated(m)=&mut r.entry else {unreachable!()};m.previous_revision+=1;m.new_revision+=1;m.mutation=HistoryMutationKind::Append;m.compaction=None;m.messages=vec![old];
 recs.push(r);let p=JournalProjection::build(sid,recs).unwrap();assert!(stage(&p,true).unwrap().proof.is_none());assert_eq!(refrows(&p.records).len(),820);
 // Valid reset changes absolute row offsets; decline.
 let mut recs=src.records.clone();if let JournalEntry::HistoryMutated(m)=&mut recs.last_mut().unwrap().entry {m.compaction=None;}
 let p=JournalProjection::build(sid,recs).unwrap();assert!(stage(&p,true).unwrap().proof.is_none());assert_eq!(refrows(&p.records).len(),100);
 // A real failed/tool/model turn after a large plain prefix: fallback gets its
 // response by later lifecycle evidence and preserves the terminal failure.
 let mut recs=src.records[..src.records.len()-1].to_vec(); // no compaction shortcut
 let mut turn=mixed_turn(0,sid,last.thread_id.unwrap());
 let seq=recs.last().unwrap().session_seq;
 for r in &mut turn {
    r.session_seq+=seq;
    match &mut r.entry{
     JournalEntry::TurnOpened(t)=>t.base_history_revision=seq,
     JournalEntry::HistoryMutated(m)=>{m.previous_revision+=seq;m.new_revision+=seq;},_=>{}
    }
 }
 let n=recs.len();
 recs.extend(turn);let p=JournalProjection::build(sid,recs.clone()).unwrap();
 // Opening a turn and appending new user text alone cannot move older rows.
 let head=JournalProjection::build(sid,recs[..n+2].to_vec()).unwrap();
 assert!(stage(&head,true).unwrap().proof.is_some());
 // The interim arrives after the last text row. It can supply dates; even before
 // the response/commit becomes visible, its very presence must veto the proof.
 let interim=JournalProjection::build(sid,recs[..n+4].to_vec()).unwrap();
 assert!(stage(&interim,true).unwrap().proof.is_none());
 // A failure with no model or tools must also veto; success is harmless.
 let mut terminal=recs.last().unwrap().clone(); let mut simple=recs[..n+2].to_vec();terminal.session_seq=simple.last().unwrap().session_seq+1;
 simple.push(terminal); let failure=JournalProjection::build(sid,simple.clone()).unwrap();
 assert!(stage(&failure,true).unwrap().proof.is_none());
 let JournalEntry::TurnSettled(t)=&mut simple.last_mut().unwrap().entry else{unreachable!()};t.status=TurnSettlementStatus::Success;t.error=None;
 let success=JournalProjection::build(sid,simple).unwrap();let s=stage(&success,true).unwrap();let mut pages=s.proof.unwrap().seal(s.file).unwrap();
 let complete=refrows(&success.records);assert_eq!(serde_json::to_vec(&complete[complete.len()-50..]).unwrap(), serde_json::to_vec(&pages.page(pages.rows,50).unwrap().0).unwrap());

 let s=stage(&p,true).unwrap();assert!(s.proof.is_none());let rows=replay(s).unwrap();
 assert_eq!(serde_json::to_vec(&rows).unwrap(),serde_json::to_vec(&refrows(&p.records)).unwrap());
 assert!(rows.last().unwrap().text.contains("workflow failed"));
}
#[test]
fn bench_window(){
 if std::env::var_os("R14_TAIL_BENCH").is_none(){return}
 let rows:usize=std::env::var("R14_TAIL_BENCH").unwrap().parse().unwrap();
 let now=Instant::now();let proj=archive(rows,100,false,true);println!("validated_fixture_setup_ms={:.3}",now.elapsed().as_secs_f64()*1e3);
 let mut expected=None;
 for candidate in [false,true,true,false]{
  let now=Instant::now();let s=stage(&proj,candidate).unwrap();let stage_ms=now.elapsed().as_secs_f64()*1e3;
  let staged=s.file.metadata().unwrap().len();let now=Instant::now();
  let data=if candidate {
   let mut p=s.proof.unwrap().seal(s.file).unwrap();
   let (page,reads,bytes)=p.page(p.rows,50).unwrap();
   let ms=now.elapsed().as_secs_f64()*1e3;
   let t=Instant::now();let (old,old_reads,old_bytes)=p.page(rows as u64/2+17,50).unwrap();
   let oldms=t.elapsed().as_secs_f64()*1e3;
   println!("mode=index rows={rows} staged={staged} index_bytes={} stage_ms={stage_ms:.3} first_ms={ms:.3} combined_ms={:.3} tail_records={reads} tail_bytes={bytes} old_ms={oldms:.3} old_records={old_reads} old_bytes={old_bytes}",rows.div_ceil(100)*24,stage_ms+ms);
   (serde_json::to_vec(&page).unwrap(),serde_json::to_vec(&old).unwrap())
  }else{
   let all=replay(s).unwrap();let ms=now.elapsed().as_secs_f64()*1e3;
   println!("mode=R13 rows={rows} staged={staged} stage_ms={stage_ms:.3} full_render_ms={ms:.3} combined_ms={:.3}",stage_ms+ms);
   (serde_json::to_vec(&all[rows-50..]).unwrap(),serde_json::to_vec(&all[rows/2+17-50..rows/2+17]).unwrap())
  };
  if let Some(x)=&expected { assert_eq!(x,&data) }else{expected=Some(data);}
 }
}
