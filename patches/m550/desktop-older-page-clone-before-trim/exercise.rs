use super::*;
use crate::app_protocol::{AppExecutionState,AppSessionSnapshot,AppTranscriptTool,AppTranscriptSubagent,AppTranscriptBase};
use crate::domain::ImageRef;
use crate::meter::{measure,charges};
use crate::transcript::Entry;
use serde_json::{json,Value};
use std::sync::Arc;
use std::hash::{Hash,Hasher,DefaultHasher};

const BEFORE:usize=49_950;
fn model(row:usize, body:usize, tool:bool)->AppTranscriptMessage{
    AppTranscriptMessage{
        message_id:(!tool).then(||uuid::Uuid::from_u128(row as u128+1)),
        timestamp_ms:Some(row as i64),phase:None,role:if tool{"system"}else{"assistant"}.into(),
        text:if !tool {format!("{}\n{}",row,"я".repeat(body/2))}else{format!("tool {row}")},
        tool:(tool&&row%4!=0).then(||child_tool(row,body)),
        subagent:(tool&&row%4==0).then(||AppTranscriptSubagent{
            child_thread_id:format!("child-{row}"), session:None,role:"fixture".into(),description:Some("native route".into()),
            status:"completed".into(),iterations:Some(1),tools:vec![child_tool(row,body)],
        }),
        images:if tool {vec![ImageRef{id:format!("id-{row}"),path:"/synthetic/preview.png".into(),name:"image".into(),mime_type:"image/png".into()}]}else{vec![]},
        streaming:false,
    }
}
fn child_tool(row:usize,body:usize)->AppTranscriptTool{
    AppTranscriptTool {
        terminal:None,call_id:format!("tool-{row}"),name:"display-fixture".into(),
        // Large nested argument payloads are passed through AppTranscriptTool,
        // not a command to execute. No actual tool/model is called.
        args:json!({"z":row,"a":{"body":"x".repeat(body)}}),
        effective_args:Some(json!({"displayed":[row,1]})),
        status:"done".into(),result:Some(format!("settled {row}")),metadata:json!({"time":row}),
    }
}
fn page(start:usize,count:usize,text:usize)->AppTranscriptPage{
    let wire=serde_json::to_string(&AppTranscriptPage{
        start,total:50_000,revision:"wire-v1".into(),
        base:Some(AppTranscriptBase{revision:"prior".into(),common_prefix:49900}),
        messages:(start..start+count).map(|i|model(i,text,false)).collect(),
    }).unwrap();
    serde_json::from_str(&wire).unwrap()
}
fn fresh(tool_bytes:usize)->(History,Transcript) {
    let snapshot=AppSessionSnapshot{
        session_id:uuid::Uuid::from_u128(1),stream_id:"native".into(),seq:1,root_thread_id:Some(uuid::Uuid::from_u128(22)),
        transcript:(BEFORE..BEFORE+50).map(|i|model(i,tool_bytes,true)).collect(),
        history:Some(AppTranscriptCursor{before:BEFORE,revision:"wire-v1".into(),base:None}),
        execution:AppExecutionState::default(),
    };
    let wire=serde_json::to_string(&snapshot).unwrap();
    let incoming:AppSessionSnapshot=serde_json::from_str(&wire).unwrap();
    let mut h=History::default();
    let mut t=Transcript::default();
    t.set_root_thread(incoming.root_thread_id);
    h.apply(&mut t,incoming.transcript,incoming.history);
    (h,t)
}
fn digest(e:&[Entry])->u64{
    let mut h=DefaultHasher::new();
    for x in e {
        (x.key,x.message_id,x.role,x.text.as_ref(),x.streaming,x.time).hash(&mut h);
        serde_json::to_vec(&x.images).unwrap().hash(&mut h);
        serde_json::to_vec(&x.tool).unwrap().hash(&mut h);
        serde_json::to_vec(&x.subagent).unwrap().hash(&mut h);
    }
    h.finish()
}
fn same_live_row(retained:&Entry,live:&Entry){
    assert_eq!(retained.key,live.key);
    assert!(Arc::ptr_eq(&retained.text,&live.text));
    assert_eq!(digest(std::slice::from_ref(retained)),digest(std::slice::from_ref(live)));
}
#[test]
fn first_page_budget_anchor_context_and_candidate_charges() {
    for (name,older_text,tool_bytes,visible,ctx) in [
        ("tight",128*1024,128*1024,0..3,None),
        ("full-viewport",128*1024,128*1024,0..50,None),
        ("fractional",128*1024,128*1024,0..3,Some(45)),
        ("ordinary",32,32,0..7,None),
        ("indivisible-page",256*1024,64*1024,0..0,None),
    ] {
        let (mut h,t)=fresh(tool_bytes);
        let req=h.request(Direction::Older,&t).unwrap();
        let p=page(BEFORE-50,50,older_text);
        if let Some(at)=ctx {
            h.context_seek=Some(ContextSeek::new(ScrollTarget{row:BEFORE+at,fraction:0.75}));
        }
        let left=charges();
        let (changes,alloc)=measure(||h.accept_page(&t,Direction::Older,&req,p,visible.clone()).expect("exact revision binds older page"));
        let visited=charges()-left;
        assert!(h.displayed(&t).proof_window_state_matches(&t));
        let e=h.displayed(&t).entries();
        assert!(e.len()>=50+visible.end);
        assert_eq!(h.range(&t),Some(HistoryRange {start:BEFORE-50,rows:e.len(),total:50_000}));
        assert_eq!(changes[0],Change::Spliced{start:0,removed:0,inserted:50});
        assert_eq!(changes.get(1).copied(),(e.len()<100).then_some(Change::Spliced{start:e.len(),removed:100-e.len(),inserted:0}));
        assert_eq!(changes.len(),if e.len()<100{2}else{1});
        for (row,x) in e[..50].iter().enumerate(){
            assert_eq!(x.key,(51+row) as u64);
            assert!(x.text.starts_with(&(BEFORE-50+row).to_string()));
        }
        for (retained,live) in e[50..].iter().zip(t.entries()){
            same_live_row(retained,live);
        }
        assert_eq!(t.entries().len(),50,"the live tail remains owned and complete");
        if ctx.is_some(){
            let measured=h.context_seek.as_ref().unwrap();
            assert_eq!(measured.rows,50);
            assert_eq!(measured.bytes,e[..50].iter().map(Entry::retained_bytes).sum::<usize>());
            assert!(e.len()>=50+1+ctx.unwrap());
        }
        if name=="ordinary"||name=="full-viewport"{assert_eq!(e.len(),100);}
        if name=="tight"{assert!((53..80).contains(&e.len()));}
        if name=="indivisible-page"{assert_eq!(e.len(),50);}
        println!("CASE {name} {} {visited} {} {} {}",e.len(),alloc.requests,alloc.bytes,digest(e));
    }
}

#[test]
fn newer_page_and_live_merge_under_the_same_retained_keys() {
    let (mut h,t)=fresh(128*1024);
    let req=h.request(Direction::Older,&t).unwrap();
    let first=h.accept_page(&t,Direction::Older,&req,page(BEFORE-50,50,128*1024),0..3).unwrap();
    assert_eq!(first.len(),2);
    let before=h.range(&t).unwrap();
    assert!(h.displayed(&t).proof_window_state_matches(&t));
    let current=h.displayed(&t).entries()[0].key;
    let older=h.request(Direction::Older,&t).unwrap();
    let more=h.accept_page(&t,Direction::Older,&older,page(BEFORE-100,50,32*1024),0..2).unwrap();
    assert!(!more.is_empty());
    // Select into older history and load forward through the normal newer branch.
    let moved=ScrollTarget{row:BEFORE-152,fraction:0.0};
    h.seek=Some(moved);
    let cursor=h.seek_cursor().unwrap();
    let page_start=cursor.before-50;
    h.accept_seek(&t,&cursor,page(page_start,50,128),).unwrap();
    let next=h.request(Direction::Newer,&t).unwrap();
    let start=next.before-50;
    h.accept_page(&t,Direction::Newer,&next,page(start,50,128),0..10).unwrap();
    let now=h.range(&t).unwrap();
    assert!(now.start<before.start&&now.start+now.rows>=next.before);
    println!("CHAIN {} {} {} {}",current,now.start,now.rows,digest(h.displayed(&t).entries()));
}

#[test]
fn invalid_reply_has_no_new_fast_path_effects_and_stale_request_stays_rejected() {
    let (mut h,t)=fresh(32);
    let req=h.request(Direction::Older,&t).unwrap();
    let mut invalid=page(BEFORE-50,50,0);invalid.revision="another".into();
    assert!(h.accept_page(&t,Direction::Older,&req,invalid,0..1).is_none());
    assert!(!h.archived());
    let mut invalid_start=page(BEFORE-50,50,0);invalid_start.start+=1;
    assert!(h.accept_page(&t,Direction::Older,&req,invalid_start,0..1).is_none());
    assert!(!h.archived());
    let token=h.begin_request().unwrap();let token_mismatch=token+1;
    assert!(!h.finish_request(token_mismatch));
    assert!(h.finish_request(token));
    assert!(!h.finish_request(token));
}
