use desktop_codex_wire_proof::codex::{CodexService,Error,ItemKind,Page,Item};
use proteus_codex_client::{Launch,Limits};
use std::{path::PathBuf, time::Duration};
mod meter;

fn service(max_line_bytes:usize) -> CodexService {
    let launch=Launch {
        program: PathBuf::from("python3"),
        args: vec!["-u".into(),"-c".into(),include_str!("peer.py").into()],
        cwd:std::env::current_dir().unwrap(),
        limits:Limits{max_line_bytes,request_timeout:Duration::from_secs(10),..Limits::default()},
    };
    CodexService::launch(launch).unwrap()
}

fn payload(page:&Page<Item>)->usize {
    assert_eq!(page.next_cursor.as_deref(),Some("alternate"));
    assert_eq!(page.data.len(),50);
    let mut bytes=0;
    for (i,row) in page.data.iter().rev().enumerate() {
        assert_eq!(row.id,format!("row:{i}"));
        assert_eq!(row.turn_id,format!("turn:{}",i/5));
        assert_eq!(row.timestamp_ms,Some(1000+i as i64));
        assert_eq!(row.status,if i==0 {"inProgress"} else {"completed"});
        match (i,&row.kind) {
            (0,ItemKind::Assistant{text}) => assert_eq!(text,&( "x".repeat(128*1024-1)+"\n[… показаны первые 128 КиБ]")),
            (1,ItemKind::Plan{text})=> assert_eq!(text,&"Я".repeat(64*1024)),
            (2,ItemKind::Tool{name,input,output})=>{
                assert_eq!(name,"fixture / read");
                assert_eq!(*input,serde_json::json!({"beta":[2,1],"alpha":{"path":"fixture"}}));
                let expected=if cfg!(feature="preserve_order"){r#"{"zeta":0,"alpha":true}"#}else{r#"{"alpha":true,"zeta":0}"#};
                assert_eq!(output,expected);
            },
            (3,ItemKind::Reasoning{text})=>assert_eq!(text,"a\nβ"),
            (i,ItemKind::Assistant{text}) if i%2==0 => {
                assert_eq!(text,&format!("стр:{i} {}", "я🦀\n".repeat(15200)));
                assert_eq!(text.capacity(),text.len());
            },
            (i,ItemKind::Plan{text}) if i%2==1 => {
                assert_eq!(text,&format!("стр:{i} {}", "я🦀\n".repeat(15200)));
                assert_eq!(text.capacity(),text.len());
            },
            _=>panic!("incorrect row {i}"),
        }
        if let ItemKind::Assistant{text}|ItemKind::Plan{text}=&row.kind {bytes+=text.len();}
    }
    bytes
}

fn main(){
    let svc=service(Limits::default().max_line_bytes);
    // In the product this is the worker making the request. Its allocations
    // are separate from the JSONL reader/deserializer thread.
    let (opened, mem)=meter::measure(||svc.resume("opaque-thread").unwrap());
    assert_eq!(opened.handle.current_turn().as_deref(),Some("live-turn"));
    let bytes=payload(&opened.history);
    let (paged,page_mem)=meter::measure(||opened.handle.history(Some("stored-cursor")).unwrap());
    assert_eq!(opened.history,paged);assert_eq!(payload(&paged),bytes);
    let alt=opened.handle.history(paged.next_cursor.as_deref()).unwrap();
    assert_eq!(alt.next_cursor,None);
    assert_eq!(alt.data.len(),2);
    let fallback=&alt.data[1];
    assert_eq!((fallback.id.as_str(),fallback.turn_id.as_str(),fallback.timestamp_ms,fallback.status.as_str()),("fallback","",None,"completed"));
    assert_eq!(fallback.kind,ItemKind::Assistant{text:"".into()});
    let other=&alt.data[0];
    assert_eq!((other.id.as_str(),other.turn_id.as_str(),other.timestamp_ms,other.status.as_str()),("view","then",Some(0),"completed"));
    assert_eq!(other.kind,ItemKind::Other{name:"futureKind".into(),text:"🦀 then".into()});
    for cursor in ["malformed-object","malformed-envelope"] {
        assert!(matches!(opened.handle.history(Some(cursor)),Err(Error::Protocol(msg)) if msg=="Codex omitted data array"));
    }
    let restrictive=service(1024*1024);
    // The same well-formed reply must never reach the projector if it is
    // above the configured line limit, and a peer failure is not recovered as a page.
    assert!(matches!(restrictive.resume("opaque-thread"),Err(Error::Protocol(msg)) if msg=="incoming frame exceeds byte limit"));
    println!("rows={} projected_text_bytes={bytes} open_allocations={} open_bytes={} page_allocations={} page_bytes={}",
        opened.history.data.len(),mem.requests,mem.bytes,page_mem.requests,page_mem.bytes);
}
