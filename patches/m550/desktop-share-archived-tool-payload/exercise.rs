use super::*;
use crate::{agents::codex::{Item,ItemKind},bridge,meter::{Count,measure},stamp,transcript::Entry};
use proteus_contracts::{
    app_protocol::{AppTranscriptTool, AppTranscriptSubagent},
    contracts::ToolTerminalRef,
    domain::{Event,ToolCall,ToolResult},
};
use serde_json::{Value,json};
use std::{hash::{DefaultHasher,Hash,Hasher},hint::black_box};
use uuid::Uuid;

fn row(i: usize, payload: usize, role: &str)->AppTranscriptMessage {
    let tool=(role=="system").then(|| AppTranscriptTool{
        terminal:Some(ToolTerminalRef{id:Uuid::from_u128(i as u128+100_000),title:"synthetic output".into(),tty:i%2==0}),
        call_id:format!("live-{i}"),name:"read_file".into(),
        args:json!({"path":"synthetic","projection":[null,{"before":[5,6]}]}),
        effective_args:Some(json!({"path":"resolved synthetic","id":i})),
        status:"done".into(),
        result:Some(format!("row-{i} {}", "abЖd".repeat(payload/5))),
        metadata:json!({"test":"case","info":[{"nested": ["ab", "bc"]}, i]}),
    });
    AppTranscriptMessage{
        timestamp_ms:Some(i as i64+1700000000000),message_id:Some(Uuid::from_u128(i as u128+1)),
        phase:None,role:role.into(),text:format!("synthetic row {i}"),images:vec![],tool,
        subagent:None,streaming:false,
    }
}
fn projected(payload:usize,density:usize)->Vec<AppTranscriptMessage>{
    let rows:Vec<_>=(49950..50000).map(|i|
       row(i,payload,if (i-49950)<density {"system"}else{"assistant"})
    ).collect();
    serde_json::from_slice(&serde_json::to_vec(&rows).unwrap()).unwrap()
}
fn page(start:usize,payload:usize)->AppTranscriptPage{
    let messages=(start..start+50).map(|i|
        row(i,payload,if payload!=0 {"system"}else if i%5==0 {"user"}else{"assistant"})
    ).collect();
    let typed=AppTranscriptPage{revision:"saved".into(),start,total:50000,messages,base:None};
    serde_json::from_slice(&serde_json::to_vec(&typed).unwrap()).unwrap()
}
fn fixture(payload:usize,density:usize)->(History,Transcript){
    let mut history=History::default();
    let mut live=Transcript::default();
    history.apply(&mut live,projected(payload,density),Some(AppTranscriptCursor{
        revision:"saved".into(),before:49950,base:None
    }));
    (history,live)
}
fn wiretool(entry:&Entry)->&AppTranscriptTool{entry.tool.as_ref().unwrap()}
fn resultptr(entry:&Entry)->*const u8{wiretool(entry).result.as_ref().unwrap().as_ptr()}
fn digest(entries:&[Entry])->u64{
    let mut h=DefaultHasher::new();
    for e in entries{
        (e.key,e.message_id,e.time,e.role,e.text.as_ref(),e.streaming,e.retained_bytes()).hash(&mut h);
        if let Some(tool)=e.tool.as_ref(){
            // The actual typed contract stays unchanged across UI ownership.
            let raw:&AppTranscriptTool=tool;
            serde_json::to_vec(raw).unwrap().hash(&mut h);
        }
    }
    h.finish()
}
fn measures(label:&str,count:Count){
    println!("MEM {label} {} {} {} {} {}",count.live,count.requests,count.bytes,count.peak,count.largest);
}

#[test]
fn archived_tool_results_stay_unchanged_after_live_approval_terminal_and_finish(){
    let (mut history,mut live)=fixture(72_000,40);
    let live_before=digest(live.entries());
    let cursor=history.request(Direction::Older,&live).unwrap();
    assert_eq!(cursor.before,49950);
    let selected=page(49900,0);
    let (changes,allocation)=measure(||
        history.accept_page(&live,Direction::Older,&cursor,selected,10..15).unwrap()
    );
    let shown=history.displayed(&live);
    let first_digest=digest(shown.entries());
    assert_eq!(changes,[Change::Spliced{start:0,removed:0,inserted:50}]);
    assert_eq!(history.range(&live),Some(HistoryRange{start:49900,rows:100,total:50000}));
    assert_eq!(live_before,digest(&shown.entries()[50..]));
    let shared=shown.entries()[50..90].iter().zip(&live.entries()[..40])
        .filter(|(a,b)| resultptr(a)==resultptr(b)).count();
    let charge:usize=shown.entries().iter().map(Entry::retained_bytes).sum();
    assert!(charge<CACHE_BYTES);
    assert_eq!(bridge::chain_tools(&shown.entries()[50..90]).len(),40);
    assert_eq!(bridge::entries(&bridge::Session{transcript:shown,key:bridge::Key(true)},50..51)[0].tool.as_ref().unwrap().result,
        wiretool(&shown.entries()[50]).result);
    measures("first-older",allocation);
    println!("MODEL first-older 100 {shared} {charge} {first_digest}");

    let thread=Uuid::from_u128(444);
    live.set_root_thread(Some(thread));
    let terminal=ToolTerminalRef{id:Uuid::from_u128(1777),title:"new terminal".into(),tty:false};
    let call="live-49950";
    let events=[
        Event::ToolCallResolved {call:ToolCall::new(call,"read_file",json!({"path":"after hooks"}))},
        Event::ToolTerminalBound {call_id:call.into(),terminal:terminal.clone()},
        Event::ApprovalRequested {call_id:call.into(),reason:"fixture requires approval".into()},
        Event::ApprovalResolved {call_id:call.into(),approved:true},
        Event::ToolFinished {result:ToolResult::ok(call.into(),"new live result").with_metadata(json!({"new":"metadata"}))},
    ];
    let archived_old=wiretool(&history.displayed(&live).entries()[50]);
    let expected_len=archived_old.result.as_ref().unwrap().len();
    assert!(expected_len>71_000);
    for event in events {assert_eq!(live.apply_runtime(thread,&event),Change::Updated(0));}
    let shown=history.displayed(&live);
    assert_eq!(digest(shown.entries()),first_digest);
    assert_ne!(resultptr(&shown.entries()[50]),resultptr(&live.entries()[0]));
    assert_eq!(wiretool(&shown.entries()[50]).result.as_ref().unwrap().len(),expected_len);
    let updated=wiretool(&live.entries()[0]);
    assert_eq!(updated.result.as_deref(),Some("new live result"));
    assert_eq!(updated.effective_args,Some(json!({"path":"after hooks"})));
    assert_eq!(updated.metadata,json!({"new":"metadata"}));
    let unchanged_shared=shown.entries()[51..90].iter().zip(&live.entries()[1..40])
        .filter(|(a,b)|resultptr(a)==resultptr(b)).count();
    let end=stamp::turn_end(shown.entries(),100,true).unwrap().time;
    assert_eq!(end,shown.entries().last().unwrap().time);
    assert_eq!(history.latest(&live),[Change::Spliced{start:0,removed:50,inserted:0}]);
    assert_eq!(history.range(&live),Some(HistoryRange{start:49950,rows:50,total:50000}));
    println!("MODEL live-update 50 {unchanged_shared} {} {}",live.entries().iter().map(Entry::retained_bytes).sum::<usize>(),digest(live.entries()));
    // Releasing the archive frees the dormant reference. The next event
    // on a previously shared row updates in place rather than re-cloning.
    let prior=resultptr(&live.entries()[1]);
    let later=Event::ApprovalRequested {call_id:"live-49951".into(),reason:"fixture".into()};
    let (change,after_drop)=measure(||live.apply_runtime(thread,&later));
    assert_eq!(change,Change::Updated(1));
    assert_eq!(resultptr(&live.entries()[1]),prior);
    assert!(after_drop.bytes<50);
    measures("unique-after-drop",after_drop);
}

#[test]
fn shared_tool_memory_does_not_discount_the_history_eviction_budget(){
    for (label,bytes) in [("below",15_000),("above",150_000),("mandatory",175_000)] {
        let (mut history,live)=fixture(bytes,50);
        let cursor=history.request(Direction::Older,&live).unwrap();
        let old=page(49900,bytes);
        let visible=if label=="mandatory" {25..30}else{0..5};
        let changes=history.accept_page(&live,Direction::Older,&cursor,old,visible).unwrap();
        let shown=history.displayed(&live).entries();
        let charge=shown.iter().map(Entry::retained_bytes).sum::<usize>();
        let model=digest(shown);
        assert_eq!(changes[0],Change::Spliced{start:0,removed:0,inserted:50});
        if label=="below" {
            assert_eq!(shown.len(),100);
            assert!(charge<CACHE_BYTES);
        } else {
            assert!(shown.len()<100);
            assert_eq!(changes[1],Change::Spliced{start:shown.len(),removed:100-shown.len(),inserted:0});
            assert_eq!(&live.entries()[..shown.len()-50].iter().map(|r|r.key).collect::<Vec<_>>(),
                  &shown[50..].iter().map(|r|r.key).collect::<Vec<_>>());
            if label=="mandatory" {
                assert_eq!(shown.len(),80);
                assert!(charge>CACHE_BYTES,"visible rows and active page remain indivisible");
            }
        }
        println!("MODEL {label} {} 0 {charge} {model}",shown.len());
    }
}

#[test]
fn cold_model_and_unique_runtime_update_do_not_copy_the_old_large_tool(){
    for density in [0,20,50] {
        let mut transcript=Transcript::default();
        let messages=projected(12_000,density);
        let (change,count)=measure(||transcript.reset(messages));
        assert_eq!(change,Change::Spliced{start:0,removed:0,inserted:50});
        let label=format!("cold-{density}");
        measures(&label,count);
        println!("MODEL {label} 50 0 {} {}",transcript.entries().iter().map(Entry::retained_bytes).sum::<usize>(),digest(transcript.entries()));
        if density>0 {
            let event=Event::ApprovalRequested {call_id:"live-49950".into(),reason:"fixture".into()};
            let old_ptr=resultptr(&transcript.entries()[0]);
            let (change,delta)=measure(||transcript.apply_runtime(Uuid::from_u128(9),&event));
            assert_eq!(change,Change::Updated(0));
            assert_eq!(wiretool(&transcript.entries()[0]).status,"waiting_approval");
            assert_eq!(resultptr(&transcript.entries()[0]),old_ptr);
            assert!(delta.bytes<50);
            measures(&format!("unique-{density}"),delta);
        }
    }
}

#[test]
fn codex_delta_and_replacement_do_not_reopen_or_mutate_archived_display(){
    let mut live=Transcript::default();
    let codex_item=|status:&str,output:String| Item {
        id:"opaque".into(),turn_id:"turn".into(),status:status.into(),timestamp_ms:Some(17),
        kind:ItemKind::Tool {name:"opaque-tool".into(),input:json!({"id":27}),output},
    };
    assert_eq!(live.external_upsert(codex_item("inProgress","old".repeat(24*1024))),Change::Pushed);
    let archive=live.clone();
    let first=wiretool(&archive.entries()[0]).result.as_ref().unwrap().len();
    assert_eq!(live.external_delta("turn","opaque","-increment 🦀",false,true),Change::Updated(0));
    assert_eq!(wiretool(&archive.entries()[0]).result.as_ref().unwrap().len(),first);
    assert!(wiretool(&live.entries()[0]).result.as_ref().unwrap().ends_with("-increment 🦀"));
    assert_eq!(live.external_upsert(codex_item("done","verified".into())),Change::Updated(0));
    assert_eq!(live.external_delta("turn","opaque","late",false,true),Change::None);
    assert_eq!(live.external_upsert(codex_item("inProgress","stale".into())),Change::None);
    assert_eq!(wiretool(&live.entries()[0]).result.as_deref(),Some("verified"));
    assert_eq!(wiretool(&archive.entries()[0]).status,"running");
    assert_eq!(archive.entries()[0].key,live.entries()[0].key);
    println!("MODEL codex 1 0 {} {}",live.entries()[0].retained_bytes(),digest(live.entries()));
}
