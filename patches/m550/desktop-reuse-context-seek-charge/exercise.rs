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

fn tool_page(start:usize, objects:usize) -> AppTranscriptPage {
    let messages=(start..start+PAGE_ROWS).map(|ordinal|{
        let mut row=model(ordinal,0,true);
        let tool=if let Some(t)=row.tool.as_mut(){t}else{&mut row.subagent.as_mut().unwrap().tools[0]};
        tool.args=serde_json::Value::Array((0..objects).map(|i|{
            // Nested display values in synthetic tool arguments, never executed.
            json!([i,{"args":[true,"я",&[i,i+1]]}])
        }).collect());
        row
    }).collect();
    let page=AppTranscriptPage{start,total:50_000,revision:"wire-v1".into(),base:None,messages};
    let body=serde_json::to_vec(&page).unwrap();
    serde_json::from_slice(&body).unwrap()
}
fn context_probe(h:&mut History,t:&Transcript,direction:Direction)->(ScrollTarget,usize){
    let shape=h.range(t).unwrap();
    let row=match direction{
        Direction::Older=>shape.start,
        Direction::Newer=>shape.start+shape.rows-1,
    };
    let target=ScrollTarget{row,fraction:0.625};
    assert_eq!(seek_context(shape,target),Some(direction),
        "exercise a raw clipped edge; actual ContextSeek::step schedules the same direction");
    h.context_seek=Some(ContextSeek::new(target));
    (target,row-shape.start)
}
fn assert_probe(h:&History,t:&Transcript,target:ScrollTarget,count:usize,bytes:usize){
    let state=h.context_seek.as_ref().unwrap();
    assert_eq!((state.rows,state.bytes,state.target),(count,bytes,target));
    let shape=h.range(t).unwrap();
    assert!( (shape.start..shape.start+shape.rows).contains(&target.row));
    let port=h.displayed(t).entries();
    let retained=&port[target.row-shape.start];
    assert!(retained.text.starts_with(&target.row.to_string())||retained.text==Arc::from(format!("tool {}",target.row)));
}
fn context_record(
    tag:&str,h:&History,t:&Transcript,target:ScrollTarget,delta:&[Change],
    charges_before:usize,values_before:usize,alloc:crate::meter::Count,
){
    let visits=charges()-charges_before;
    let json_visits=crate::meter::values()-values_before;
    let e=h.displayed(t).entries();
    let r=h.range(t).unwrap();
    let mut a=DefaultHasher::new();
    format!("{delta:?} {r:?} {target:?}").hash(&mut a);
    println!("EDGE {tag} {} {visits} {json_visits} {} {} {} {}",e.len(),alloc.requests,alloc.bytes,digest(e),a.finish());
}
#[test]
fn semantic_context_first_page_existing_edges_and_resume() {
    // The first live edge follows the same fractional route as an already
    // archived edge; it must not materialize discarded live rows from #616.
    let (mut h,t)=fresh(128*1024);
    let (target,local)=context_probe(&mut h,&t,Direction::Older);
    let request=h.request(Direction::Older,&t).unwrap();
    let incoming=tool_page(request.before-PAGE_ROWS,240);
    // Charge reference on a separate key space; do not preallocate any
    // archive/live row identities consumed by this test.
    let mut independent=Transcript::default();
    independent.reset(incoming.messages.clone());
    let sum=independent.entries().iter().map(Entry::retained_bytes).sum::<usize>();
    assert!(sum<CACHE_BYTES);
    let (c,v)=(charges(),crate::meter::values());
    let (delta,alloc)=measure(||h.accept_page(&t,Direction::Older,&request,incoming,local..local+1).unwrap());
    context_record("first-edge",&h,&t,target,&delta,c,v,alloc);
    assert_probe(&h,&t,target,PAGE_ROWS,sum);
    assert!(h.displayed(&t).proof_window_state_matches(&t));

    for (label,direction,objects) in [
        ("older-within",Direction::Older,240),
        ("newer-within",Direction::Newer,240),
        ("older-equal",Direction::Older,240),
        ("newer-equal",Direction::Newer,240),
        ("older-over",Direction::Older,1650),
        ("newer-over",Direction::Newer,1650),
    ] {
        let (mut h,t)=fresh(120*1024);
        h.seek=Some(ScrollTarget{row:BEFORE-150,fraction:0.0});
        let req=h.seek_cursor().unwrap();let start=req.before-PAGE_ROWS;
        h.accept_seek(&t,&req,page(start,PAGE_ROWS,56*1024)).unwrap();
        let (target,local)=context_probe(&mut h,&t,direction);
        let request=h.request(direction,&t).unwrap();
        let mut incoming=tool_page(request.before-PAGE_ROWS,objects);
        let mut oracle=Transcript::default();oracle.reset(incoming.messages.clone());
        let mut sum=oracle.entries().iter().map(Entry::retained_bytes).sum::<usize>();
        if label.ends_with("-equal") {
            assert!(sum<CACHE_BYTES);
            incoming.messages[0].text.push_str(&"x".repeat(CACHE_BYTES-sum));
            incoming=serde_json::from_slice(&serde_json::to_vec(&incoming).unwrap()).unwrap();
            oracle.reset(incoming.messages.clone());
            sum=oracle.entries().iter().map(Entry::retained_bytes).sum::<usize>();
        }
        use std::cmp::Ordering::{Less,Equal,Greater};
        assert_eq!(sum.cmp(&CACHE_BYTES),if label.ends_with("-over"){Greater}else if label.ends_with("-equal"){Equal}else{Less},"force each aggregate cap edge");
        let (c,v)=(charges(),crate::meter::values());
        let (delta,alloc)=measure(||h.accept_page(&t,direction,&request,incoming,local..local+1).unwrap());
        context_record(label,&h,&t,target,&delta,c,v,alloc);
        assert_probe(&h,&t,target,PAGE_ROWS,sum);
        if !label.ends_with("-within"){assert_eq!(h.displayed(&t).entries().len(),PAGE_ROWS+1);}
    }

    let (mut h,t)=fresh(128*1024);
    let req=h.request(Direction::Older,&t).unwrap();
    h.accept_page(&t,Direction::Older,&req,page(BEFORE-PAGE_ROWS,PAGE_ROWS,128*1024),0..3).unwrap();
    let (target,local)=context_probe(&mut h,&t,Direction::Newer);
    assert!(h.request(Direction::Newer,&t).is_none(),"the remaining rows now come from live");
    let offset=h.archive.as_ref().unwrap().end()-BEFORE;
    assert!(offset>0&&offset<t.entries().len());
    let slice=&t.entries()[offset..];
    let sum=slice.iter().map(Entry::retained_bytes).sum::<usize>();
    let (c,v)=(charges(),crate::meter::values());
    let (delta,alloc)=measure(||h.merge_tail(&t,local..local+1));
    context_record("return-live",&h,&t,target,&delta,c,v,alloc);
    assert_probe(&h,&t,target,slice.len(),sum);
    assert_eq!(h.displayed(&t).entries().last().unwrap().key,t.entries().last().unwrap().key);
}
