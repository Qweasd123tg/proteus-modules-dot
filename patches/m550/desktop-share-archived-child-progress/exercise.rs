use super::*;
use crate::{bridge,meter::{Count,measure},transcript::Entry};
use proteus_contracts::{
    app_protocol::AppTranscriptSubagent,
    contracts::ToolTerminalRef,
    domain::{Event,ToolCall,ToolResult},
};
use serde_json::json;
use std::hash::{Hash,Hasher,DefaultHasher};
use uuid::Uuid;

fn cursor()->AppTranscriptCursor{AppTranscriptCursor{revision:"verified".into(),before:49950,base:None}}
fn row(i:usize)->AppTranscriptMessage{
    AppTranscriptMessage {
        timestamp_ms:Some(i as i64),message_id:Some(Uuid::from_u128(i as u128+1)),phase:None,
        role:if i%7==0 {"user"}else{"assistant"}.into(),text:format!("synthetic row {i}"),
        images:vec![],tool:None,subagent:None,streaming:false,
    }
}
fn page()->AppTranscriptPage{
    let p=AppTranscriptPage{revision:"verified".into(),start:49900,total:50000,
       messages:(49900..49950).map(row).collect(),base:None};
    serde_json::from_slice(&serde_json::to_vec(&p).unwrap()).unwrap()
}
fn active(n:u128)->Uuid{Uuid::from_u128(118_000+n)}
fn child(entry:&Entry)->&AppTranscriptSubagent{entry.subagent.as_ref().unwrap()}
fn tools_ptr(entry:&Entry)->*const u8{child(entry).tools.as_ptr().cast()}
fn status_child(live:&Transcript,i:usize)->&AppTranscriptSubagent{child(&live.entries()[i])}
fn call(id:&str)->Event{Event::ToolCallRequested{call:ToolCall::new(id,"read_file",json!({"path":"synthetic","params":[1,2,3]}))}}
fn begin(id:Uuid)->Event{Event::SubagentStarted{role:"researcher".into(),description:Some("synthetic project".into()),child_thread_id:id}}
fn finish_tool(id:&str,n:usize)->Event{
    Event::ToolFinished {result:ToolResult::ok(id.into(),"example Ж\n".repeat(n/11)).with_metadata(json!({
       "preview":[{"source":"fixture","id":id,"exact":1.2}], "when":"candidate"
    }))}
}
fn print(label:&str,c:Count){println!("MEM {label} {} {} {} {} {}",c.live,c.requests,c.bytes,c.peak,c.largest);}
fn model(rows:&[Entry])->(usize,u64){
    let mut h=DefaultHasher::new();
    let mut total=0;
    for row in rows{
        let charge=row.retained_bytes();total+=charge;
        (row.key,row.message_id,row.role,row.text.as_ref(),row.time,charge,row.streaming).hash(&mut h);
        if let Some(ag)=row.subagent.as_ref(){
            let owned:&AppTranscriptSubagent=ag;
            serde_json::to_vec(owned).unwrap().hash(&mut h);
        }
    }
    (total,h.finish())
}
fn model_line(label:&str, rows:&[Entry],shared:usize){
    let (charge,hash)=model(rows);
    println!("MODEL {label} {} {shared} {charge} {hash}",rows.len());
}
fn fixture(a:usize,b:usize,bytes:usize)->(History,Transcript){
    let mut history=History::default();
    let mut live=Transcript::default();
    let prior:Vec<_>=(49950..49998).map(row).collect();
    let prior=serde_json::from_slice(&serde_json::to_vec(&prior).unwrap()).unwrap();
    history.apply(&mut live,prior,Some(cursor()));
    for (offset,id,len) in [(48,active(1),a),(49,active(2),b)] {
        assert_eq!(live.apply_runtime(active(0),&begin(id)),Change::Pushed);
        for step in 0..len{
            let callid=format!("{id}-{step:02}");
            assert_eq!(live.apply_runtime(id,&call(&callid)),Change::Updated(offset));
            assert_eq!(live.apply_runtime(id,&finish_tool(&callid,bytes)),Change::Updated(offset));
        }
    }
    (history,live)
}
fn old_page(history:&mut History,live:&Transcript,visible:Range<usize>)->Vec<Change>{
    let req=history.request(Direction::Older,live).unwrap();
    history.accept_page(live,Direction::Older,&req,page(),visible).unwrap()
}
#[test]
fn runtime_child_progress_shares_first_older_until_that_child_changes(){
    let (mut history,mut live)=fixture(48,64,52_800);
    let req=history.request(Direction::Older,&live).unwrap();
    let saved=page();
    let (edit,memory)=measure(|| history.accept_page(&live,Direction::Older,&req,saved,0..50).unwrap());
    assert_eq!(edit,[Change::Spliced{start:0,removed:0,inserted:50}]);
    assert_eq!(history.range(&live),Some(HistoryRange{start:49900,rows:100,total:50000}));
    let archive=history.displayed(&live);
    let expected=model(archive.entries());
    let shared=[48,49].iter().filter(|n|
        tools_ptr(&archive.entries()[50+**n])==tools_ptr(&live.entries()[**n])
    ).count();
    assert_eq!(status_child(&live,48).tools.len(),48);
    assert_eq!(status_child(&live,49).tools.len(),64);
    let display_dto=bridge::entries(&bridge::Session{transcript:archive,key:bridge::Key(true)},98..99);
    assert_eq!(serde_json::to_value(display_dto[0].subagent.as_ref().unwrap()).unwrap(),serde_json::to_value(child(&archive.entries()[98])).unwrap());
    model_line("first-older",archive.entries(),shared);
    print("first-older",memory);
    let missing=Event::ApprovalRequested{call_id:"no-match".into(),reason:"fixture".into()};
    let (change,no_match)=measure(||live.apply_runtime(active(0),&missing));
    assert_eq!(change,Change::None);
    assert!(no_match.bytes<32);
    print("failed-probe",no_match);

    let new_at_cap=call("not-stored-at-cap");
    let capped_ptr=tools_ptr(&live.entries()[49]);
    let (change,capped)=measure(||live.apply_runtime(active(2),&new_at_cap));
    assert_eq!(change,Change::Updated(49));
    assert_eq!(status_child(&live,49).tools.len(),64);
    assert_eq!(tools_ptr(&live.entries()[49]),capped_ptr);
    assert!(capped.bytes<3500);
    print("full-child",capped);

    let a=active(1);
    let a_first=format!("{a}-00");
    let terminal=ToolTerminalRef{id:Uuid::from_u128(400),title:"fixture opened".into(),tty:true};
    let events=[
        Event::ToolCallResolved{call:ToolCall::new(&a_first,"read_file",json!({"path":"resolved confirmed"}))},
        Event::ToolTerminalBound{call_id:a_first.clone(),terminal:terminal.clone()},
        Event::ApprovalRequested{call_id:a_first.clone(),reason:"fixture".into()},
        Event::ApprovalResolved{call_id:a_first.clone(),approved:true},
        finish_tool(&a_first,127),
        call("additional-progress"),
        Event::SubagentSessionBound{child_thread_id:a,session_id:Uuid::from_u128(91),session_dir:"/synthetic/exact-child".into()},
        Event::SubagentFinished{role:"researcher".into(),status:"completed".into(),iterations:49,child_thread_id:a},
    ];
    for ev in events{assert_eq!(live.apply_runtime(a,&ev),Change::Updated(48));}
    let live_a=status_child(&live,48);
    assert_eq!(live_a.tools.len(),49);
    assert_eq!(live_a.tools[0].terminal,Some(terminal));
    assert_eq!(live_a.tools[0].effective_args,Some(json!({"path":"resolved confirmed"})));
    assert_eq!(live_a.iterations,Some(49));
    assert_eq!(live_a.session.as_ref().unwrap().session_id,Uuid::from_u128(91));
    assert_eq!(live_a.status,"completed");
    let archive=history.displayed(&live);
    assert_eq!(model(archive.entries()),expected);
    assert_ne!(tools_ptr(&archive.entries()[98]),tools_ptr(&live.entries()[48]));
    assert_eq!(tools_ptr(&live.entries()[49]),capped_ptr);
    let still_shared=usize::from(tools_ptr(&archive.entries()[99])==capped_ptr);
    model_line("live-update",live.entries(),still_shared);
    assert_eq!(history.latest(&live),[Change::Spliced{start:0,removed:50,inserted:0}]);
    assert_eq!(history.range(&live),Some(HistoryRange{start:49950,rows:50,total:50000}));
    let next=Event::ApprovalRequested{call_id:format!("{}-00",active(2)),reason:"fixture".into()};
    let (change,released)=measure(||live.apply_runtime(active(2),&next));
    assert_eq!(change,Change::Updated(49));
    assert!(released.bytes<50);
    assert_eq!(tools_ptr(&live.entries()[49]),capped_ptr);
    print("after-drop",released);
}

#[test]
fn nested_tool_collision_keeps_last_match_across_and_within_children(){
    let (mut history,mut live)=fixture(1,1,1024);
    for who in [active(1),active(2),active(2)]{
        live.apply_runtime(who,&call("reused-call"));
    }
    old_page(&mut history,&live,0..50);
    let terminal=ToolTerminalRef{id:Uuid::from_u128(17),title:"fixture".into(),tty:false};
    assert_eq!(live.apply_runtime(active(2),&Event::ToolTerminalBound{call_id:"reused-call".into(),terminal:terminal.clone()}),Change::Updated(49));
    assert!(status_child(&live,48).tools[1].terminal.is_none());
    assert!(status_child(&live,49).tools[1].terminal.is_none());
    assert_eq!(status_child(&live,49).tools[2].terminal.as_ref(),Some(&terminal));
    assert!(child(&history.displayed(&live).entries()[99]).tools[2].terminal.is_none());
    model_line("duplicate",live.entries(),0);
}

#[test]
fn pressure_discards_or_preserves_child_rows_by_the_exact_existing_budget(){
    // History init test harness uses actual runtime-produced, typed rows.
    let (mut drop_history,live)=fixture(48,64,99_000);
    let changes=old_page(&mut drop_history,&live,0..1);
    let dropped=drop_history.displayed(&live).entries();
    assert_eq!(dropped.len(),99); // first child fits, second does not
    assert_eq!(changes[1],Change::Spliced{start:99,removed:1,inserted:0});
    assert_eq!(child(&dropped[98]).child_thread_id,active(1).to_string());
    assert!(model(dropped).0<CACHE_BYTES);
    model_line("pressure-tail",dropped,0);
    let (mut keep_history,live)=fixture(48,64,99_000);
    let changes=old_page(&mut keep_history,&live,48..50);
    let kept=keep_history.displayed(&live).entries();
    assert_eq!(kept.len(),100);
    assert_eq!(changes.len(),1);
    assert!(model(kept).0>CACHE_BYTES);
    model_line("pressure-visible",kept,0);
}

#[test]
fn supplied_typed_child_snapshot_replaces_changed_public_metadata(){
    let (_history,mut live)=fixture(1,1,1024);
    let old=live.clone();
    let selected=status_child(&live,49).clone();
    let mut payload=row(1234);
    payload.role="system".into();
    payload.message_id=None;
    payload.subagent=Some(selected.clone());
    live.reset(vec![payload.clone()]);
    let key=live.entries()[0].key;
    payload.subagent.as_mut().unwrap().tools[0].metadata=json!({"replacement":"fresh owned body"});
    let after:Vec<AppTranscriptMessage>=serde_json::from_slice(&serde_json::to_vec(&vec![payload]).unwrap()).unwrap();
    live.reset(after);
    assert_eq!(live.entries()[0].key,key);
    assert_eq!(old.entries()[49].subagent.as_ref().unwrap().tools[0].metadata,selected.tools[0].metadata);
    assert_eq!(status_child(&live,0).tools[0].metadata,json!({"replacement":"fresh owned body"}));
    model_line("snapshot-replace",live.entries(),0);
}
