use crate::{
    app_protocol::{AppSubagentSession, AppTranscriptMessage, AppTranscriptPage, AppTranscriptSubagent},
    core_projection::JournalProof,
    domain::{SubagentSessionBinding, ToolCall, ToolResult},
    history::present_page,
    meter::{decodes, measure},
    row_layout::row_context,
    stamp::{hidden, turn_end},
    transcript::{Change, Entry, Transcript, affected_rows, subagent::{is_task, progress_row, task_session, task_status}},
};
use serde_json::{Value, json};
use std::{hint::black_box, path::PathBuf};
use uuid::Uuid;

fn text_row(i: usize, role: &str) -> AppTranscriptMessage {
    AppTranscriptMessage {
        message_id: Some(Uuid::from_u128(1+i as u128)), phase: None,
        timestamp_ms: Some(1_700_000_000_000+i as i64),
        role: role.into(), text: format!("synthetic row {i}"), images: vec![],
        tool: None, subagent: None, streaming: false,
    }
}
fn dir(i: usize) -> PathBuf {
    PathBuf::from(format!("/home/example/.local/share/proteus/sessions/2026/11/24/synthetic-session-{i:05}-child"))
}
fn native_page(dense:bool) -> AppTranscriptPage {
    let mut journal = JournalProof::default();
    for i in 0..50_000 {
        let role=if i%5==0 {"user"} else {"assistant"};
        let has_link= i>=49_950 && if dense {i%10!=0 && i%10!=9} else {i%5==2 || i%5==3};
        if !has_link {
            journal.push(text_row(i,role));
            continue;
        }
        let call_id=format!("call-{i}");
        let name=["spawn_agent","followup_task","task"][i%3];
        let call=ToolCall::new(call_id.clone(),name,json!({"role":"explorer","description":"synthetic read"}));
        let result=ToolResult::ok(call_id.clone(),"Synthetic result").with_metadata(json!({"test_result":true}));
        let binding=SubagentSessionBinding {
            source_call_id:call_id,child_thread_id:Uuid::from_u128(i as u128+10),
            session_id:Uuid::from_u128(i as u128+100),session_dir:dir(i)
        };
        journal.record(call,result,binding);
    }
    let page=journal.page();
    assert_eq!((page.start,page.total,page.messages.len()),(49_950,50_000,50));
    let wire=serde_json::to_vec(&page).unwrap();
    serde_json::from_slice(&wire).unwrap()
}

#[test]
fn saved_page_keeps_every_card_link_and_footer_on_the_first_visible_tail() {
    for (label,dense,activity,visible) in [("mixed",false,20,20),("dense",true,40,50)] {
        let (transcript,range,changes)=present_page(native_page(dense));
        let rows=transcript.entries();
        assert_eq!(changes,[Change::Spliced {start:0,removed:0,inserted:50}]);
        assert!(rows.iter().all(|row| row.subagent.is_none()));
        assert_eq!(rows.iter().filter_map(|r|r.tool.as_ref()).filter(|t|is_task(t)).count(),activity);
        let before=decodes();
        let rendered_start=rows.len()-visible;
        let ((cards,footers,digest),count)=measure(||{
            // Thread::prepare_turn_stamp then RowContext and visible row presentation.
            let last=rows.iter().rposition(|entry| !hidden(rows,entry)).unwrap();
            let context=row_context(rows,true,Some(range));
            assert_eq!(last,49);
            assert!(!context.is_complete(0));
            assert!(context.is_complete(49));
            let mut cards=0;
            let mut footers=0;
            let mut digest=0u64;
            for row in rendered_start..rows.len() {
                let entry=&rows[row];
                assert!(!hidden(rows,entry));
                if let Some(end)=turn_end(rows,row+1,true) {
                    footers+=1;
                    digest^=(row as u64).rotate_left(27)^end.time.unwrap() as u64;
                }
                if let Some(tool)=&entry.tool {
                    // The real task-card render still decodes a validated link.
                    let link=task_session(tool).expect("saved task navigates");
                    let expect=range.start+row;
                    assert_eq!(link.session_dir,std::path::Path::new(tool.metadata["subagent_session"]["session_dir"].as_str().unwrap()));
                    assert_eq!(link.session_id,Uuid::from_u128(expect as u128+100));
                    let expected_status=if expect%3==2 {"completed"} else {"unknown"};
                    assert_eq!(task_status(tool),expected_status);
                    cards+=1;
                    digest=digest.rotate_left(3)^link.session_id.as_u128() as u64;
                }
                assert_eq!(entry.key,(row+1) as u64);
            }
            black_box((cards,footers,digest))
        });
        let rows_named=if dense {40}else{8};
        assert_eq!(cards,rows_named);
        assert!(footers>0);
        println!("DISPLAY {label} {} {visible} {cards} {footers} {} {} {} {digest}",rows.len(),decodes()-before,count.requests,count.bytes);
    }
}
fn live_session(id:u128,path:&str)->AppSubagentSession {
    AppSubagentSession {session_id:Uuid::from_u128(id),session_dir:PathBuf::from(path)}
}
fn overlay(i:usize,child:&str,session:Option<AppSubagentSession>)->AppTranscriptMessage {
    let mut row=text_row(i,"system");
    row.subagent=Some(AppTranscriptSubagent {child_thread_id:child.into(),session,
       role:"worker".into(),description:None,status:"completed".into(),iterations:Some(1),tools:vec![]});
    row
}
#[test]
fn clipped_compatible_overlay_wins_only_when_binding_allows_it() {
    let mut card=native_page(false).messages.into_iter().find(|r|r.tool.is_some()).unwrap();
    let right=live_session(5,"/saved/right");
    let wrong_id=live_session(6,"/saved/right");
    let wrong_path=live_session(5,"/saved/wrong");
    let aliases=live_session(5,"/saved/./right/");
    let entries: [(&str,Option<AppSubagentSession>);6]=[("other",Some(right.clone())),
       ("exact",Some(wrong_id)),
       ("exact",Some(wrong_path)),
       ("exact",Some(aliases)),
       ("exact",None),
       ("exact",Some(right.clone()))];
    let json_right=json!(&right);
    let mut with_unknown=json_right.clone();with_unknown["extra"]=json!(true);
    let variants=[
        ("valid",Some(json_right.clone()),Some(4),true),
        ("seq",Some(json!([right.session_id,right.session_dir])),Some(4),true),
        ("legacy",None,Some(2),false),
        ("null",Some(Value::Null),Some(2),false),
        ("string",Some(json!("ignore me")),None,false),
        ("number",Some(json!(0)),None,false),
        ("unknown",Some(with_unknown),None,false),
        ("relative",Some(json!(live_session(5,"saved/right"))),None,false),
        ("wrong-uuid",Some(json!({"session_id":"bad","session_dir":"/saved/right"})),None,false),
        ("missing-dir",Some(json!({"session_id":right.session_id})),None,false),
        ("matching-unbound",Some(json!(live_session(11,"/different/absolute"))),Some(5),true),
    ];
    let mut signature=0u64;
    for (n,v,expected,link) in variants {
        let tool=card.tool.as_mut().unwrap();
        tool.metadata=json!({"tool":"task","child_thread_id":"exact"});
        if let Some(v)=v { tool.metadata["subagent_session"]=v; }
        let mut live=vec![text_row(0,"assistant"),card.clone()];
        live.extend(entries.iter().enumerate().map(|(i,(s,session))|overlay(i+2,s,session.clone())));
        live.push(text_row(9,"user"));
        let mut model=Transcript::default();
        model.reset(live);
        let all=model.entries();
        let tool=all[1].tool.as_ref().unwrap();
        let winner=progress_row(all,tool);
        assert_eq!(winner,expected.map(|i|i+1),"{n}");
        assert_eq!(hidden(all,&all[1]),winner.is_some(),"{n}");
        assert_eq!(affected_rows(all,1),1..winner.map_or(2,|i|i+1),"{n}");
        assert_eq!(task_session(tool).is_some(),link,"{n}");
        assert!(turn_end(all,all.len(),true).is_none()); // unanswered user
        assert!(!hidden(&all[..2],&all[1]),"clipped edge: {n}");
        assert_eq!(turn_end(&all[..2],2,false).is_some(),false);
        signature=signature.rotate_left(11)^(winner.unwrap_or(0) as u64)*3+link as u64;
    }
    // Non-task metadata and wrong identity stay visible regardless of title.
    let mut spoof=card.tool.unwrap();
    spoof.metadata["tool"]=json!("not-an-agent-tool");
    assert!(progress_row(&[],&spoof).is_none());
    assert!(task_session(&spoof).is_none());
    println!("PARITY {signature}");
}
