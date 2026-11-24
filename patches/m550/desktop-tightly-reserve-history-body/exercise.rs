use crate::{
    api::Api,
    app_protocol::{AppTranscriptCursor, AppTranscriptMessage, AppTranscriptPage, AppTranscriptTool},
    core_page,
    meter::{Count,measure},
};
use serde_json::{Value,json};
use std::{io::{BufRead,BufReader,Write},net::TcpListener,path::Path,time::Duration};
use uuid::Uuid;

#[derive(Clone,Copy)]
enum Framing { Explicit(usize), Chunked, ToClose }

fn read_http(
    body:Vec<u8>, framing:Framing,status:u16, content_type:&'static str,
    endpoint:&'static str, initial:bool, step:usize,
)->(anyhow::Result<AppTranscriptPage>,Count) {
    let server=TcpListener::bind("127.0.0.1:0").unwrap();
    let origin=format!("http://{}",server.local_addr().unwrap());
    let client=Api::local_test(&origin);
    let task=std::thread::spawn(move || {
        let (mut socket,_)=server.accept().unwrap();
        socket.set_write_timeout(Some(Duration::from_secs(5))).unwrap();
        socket.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
        let mut req=BufReader::new(socket.try_clone().unwrap());
        let mut line=String::new();
        req.read_line(&mut line).unwrap();
        if endpoint!="/history/page" {
            assert_eq!(line,format!("GET {endpoint} HTTP/1.1\r\n"));
        } else if initial {
            assert_eq!(line,"GET /history/page?session_dir=%2Fsynthetic%2Froot HTTP/1.1\r\n");
        } else {
            assert_eq!(line,"GET /history/page?session_dir=%2Fsynthetic%2Froot&before=49950&revision=proof HTTP/1.1\r\n");
        }
        let mut auth=false;
        loop {
            line.clear();
            assert_ne!(req.read_line(&mut line).unwrap(),0);
            if line=="\r\n" {break;}
            auth|=line.to_ascii_lowercase()=="authorization: bearer history-proof\r\n";
        }
        assert!(auth);
        write!(socket,"HTTP/1.1 {status} Fixture\r\nContent-Type: {content_type}\r\nConnection: close\r\n").unwrap();
        match framing {
            Framing::Explicit(size)=>write!(socket,"Content-Length: {size}\r\n").unwrap(),
            Framing::Chunked=>socket.write_all(b"Transfer-Encoding: chunked\r\n").unwrap(),
            Framing::ToClose=>(),
        }
        socket.write_all(b"\r\n").unwrap();
        for chunk in body.chunks(step) {
            if matches!(framing,Framing::Chunked) {write!(socket,"{:X}\r\n",chunk.len()).unwrap();}
            socket.write_all(chunk).unwrap();
            if matches!(framing,Framing::Chunked) {socket.write_all(b"\r\n").unwrap();}
        }
        if matches!(framing,Framing::Chunked) {socket.write_all(b"0\r\n\r\n").unwrap();}
    });
    let path=Path::new("/synthetic/root");
    let cursor=AppTranscriptCursor {before:49950,revision:"proof".into(),base:None};
    let out=measure(|| if endpoint!="/history/page" {
        client.control_get(endpoint)
    } else if initial {
        client.initial_history_page(path)
    } else {
        client.history_page(path,&cursor)
    });
    task.join().unwrap();
    out
}
fn wire(fat:usize,previous:bool)->(AppTranscriptPage,Vec<u8>) {
    let end:usize=if previous {49_950}else{50_000};
    let rows=(0..50_000).map(|row| {
        let formatting=if row%4==1 {"\n↗ строка \"a\""} else {"abcd.vwxyz"};
        let has_tool=row%3!=0 && (end-50..end).contains(&row);
        AppTranscriptMessage {
            timestamp_ms:Some(1_700_000_000_000+row as i64),
            message_id:Some(Uuid::from_u128(row as u128+1)),
            phase:None,role:if has_tool{"system"}else{"assistant"}.into(),
            text:if !has_tool && (end-50..end).contains(&row) {
                "not a tool: ".to_owned()+&"cdXYZœ".repeat(fat/7)
            } else {"historical record".to_owned()},
            images:vec![],tool:has_tool.then(|| AppTranscriptTool{
                terminal:None,call_id:format!("proof-{row}"),name:"read_file".into(),
                args:json!({"metadata":{"line":17,"path":"/synthetic/result"}}),
                effective_args: None,
                status:"done".into(),
                result:Some(formatting.repeat(fat/formatting.len())),
                metadata:json!({"source":"native proof","flags":[true,null,{"preview":{"nested":1}}]}),
            }),subagent:None,streaming:false,
        }
    }).collect();
    let page=core_page::page(rows,"proof".into(),end);
    let bytes=serde_json::to_vec(&page).unwrap();
    (page,bytes)
}
fn assert_page(expected:&AppTranscriptPage,got:&AppTranscriptPage) {
    assert_eq!((got.messages.len(),got.start,got.total),(50,expected.start,50_000));
    assert_eq!(serde_json::to_value(got).unwrap(),serde_json::to_value(expected).unwrap());
}
fn print(label:&str,c:Count) {
    println!("BODY {label} {} {} {} {} {} {} {} {} {}",c.raw_len,c.raw_capacity,c.hint_received,
       c.hint_capacity,c.hint_chosen,c.requests,c.bytes,c.peak,c.largest);
}
#[test]
fn native_fixed_large_page_and_paged_cursor() {
    for (name,previous,step) in [("first",false,1027),("older",true,16381),("wide",false,65536)] {
        let (page,bytes)=wire(93_000,previous);
        let len=bytes.len();
        let (got,count)=read_http(bytes,Framing::Explicit(len),200,"application/json","/history/page",!previous,step);
        assert_page(&page,&got.unwrap());
        assert_eq!(count.raw_len,len);
        print(name,count);
    }
}
#[test]
fn fallback_lengths_and_routes_produce_exact_same_page() {
    let (page,bytes)=wire(6_100,false);
    let len=bytes.len();
    assert!((256*1024..16*1024*1024).contains(&len));
    assert!(len.next_power_of_two()-len>=64*1024);
    for (label,framing,kind,endpoint) in [
        ("chunk",Framing::Chunked,"application/json","/history/page"),
        ("close",Framing::ToClose,"application/json","/history/page"),
        ("other-type",Framing::Explicit(len),"text/plain; charset=utf-8","/history/page"),
        ("unrelated",Framing::Explicit(len),"application/json","/other"),
    ] {
        let (got,count)=read_http(bytes.clone(),framing,200,kind,endpoint,true,2101);
        assert_page(&page,&got.unwrap());
        assert_eq!(count.hint_chosen,0);
        print(label,count);
    }
    let (page,bytes)=wire(2_000,false);
    let len=bytes.len();
    let (got,count)=read_http(bytes,Framing::Explicit(len),200,"application/json","/history/page",true,2101);
    assert_page(&page,&got.unwrap());
    assert_eq!(count.hint_chosen,0);
    print("small",count);
    let (page,mut bytes)=wire(5_000,false);
    let len=bytes.len().next_power_of_two();
    bytes.resize(len,b' ');
    let (got,count)=read_http(bytes,Framing::Explicit(len),200,"application/json","/history/page",true,2101);
    assert_page(&page,&got.unwrap());
    assert_eq!(count.hint_chosen,0);
    print("power",count);
    let (page,bytes)=wire(338_000,false);
    let len=bytes.len();
    assert!(len>16*1024*1024);
    let (got,count)=read_http(bytes,Framing::Explicit(len),200,"application/json","/history/page",true,65521);
    assert_page(&page,&got.unwrap());
    assert_eq!(count.hint_chosen,0);
    print("above-plan",count);
}
#[test]
fn validation_does_not_accept_bad_text_or_incomplete_transport() {
    let (_,bytes)=wire(8_200,false);
    let len=bytes.len();
    let prefix=len.next_power_of_two()/2;
    for (label,body,framing,status) in [
       ("short-before",bytes[..prefix-7].to_vec(),Framing::Explicit(len),200),
       ("short-after",bytes[..prefix+7].to_vec(),Framing::Explicit(len),200),
       ("huge-hint",bytes[..31].to_vec(),Framing::Explicit((16*1024*1024)+1),200),
       ("http-error",br#"{"ok":false,"error":"revision has changed"}"#.to_vec(),Framing::Explicit(42),409),
    ] {
        let framing=if label=="http-error" {Framing::Explicit(body.len())} else {framing};
        let (got,count)=read_http(body,framing,status,"application/json","/history/page",true,65519);
        let error=got.unwrap_err().to_string();
        if label=="http-error" {
            assert_eq!(error,r#"GET /history/page failed with 409 Conflict: {"ok":false,"error":"revision has changed"}"#);
        } else {
            assert!(error.contains("Peer disconnected")||error.contains("UnexpectedEof")||error.contains("unexpected end"),"{label}: {error}");
            if label!="short-after" {assert_eq!(count.hint_chosen,0);}
        }
        println!("ERROR {label} {error}");
        print(label,count);
    }
    let mut big_error=br#"{"error":"history source changed"}"#.to_vec();
    big_error.resize(len,b' ');
    let (got,count)=read_http(big_error,Framing::Explicit(len),409,"application/json","/history/page",true,8191);
    let error=got.unwrap_err().to_string();
    assert_eq!(count.hint_chosen,0);
    assert_eq!(error.trim_end(),r#"GET /history/page failed with 409 Conflict: {"error":"history source changed"}"#);
    assert!(error.ends_with("        "));
    println!("ERROR large-status {}",error.trim_end());
    print("large-status",count);
    let mut invalid=bytes.clone();
    // This field would be ignored by AppTranscriptMessage's schema, but the
    // old whole-body check also validates every byte in ignored fields.
    let marker=invalid.windows(14).position(|x|x==b"\"timestamp_ms\"").unwrap();
    let injected=[b'"',b'x',b'"',b':',b'"',0xff,b'"',b','];
    invalid.splice(marker..marker,injected);
    let size=invalid.len();
    let (got,count)=read_http(invalid,Framing::Explicit(size),200,"application/json","/history/page",true,8191);
    let error=got.unwrap_err().to_string();
    assert!(error.contains("stream did not contain valid UTF-8"),"{error}");
    println!("ERROR utf8 {error}");
    print("utf8",count);
    let mut invalid_short=bytes[..prefix+30].to_vec();
    invalid_short.splice(marker..marker,injected);
    let (got,count)=read_http(invalid_short,Framing::Explicit(size),200,"application/json","/history/page",true,8191);
    let error=got.unwrap_err().to_string();
    assert!(error.contains("Peer disconnected"),"{error}");
    println!("ERROR invalid-utf8-and-short {error}");
    print("invalid-utf8-and-short",count);
    let mut invalid=bytes;
    invalid.push(b'!');
    let size=invalid.len();
    let (got,count)=read_http(invalid,Framing::Explicit(size),200,"application/json","/history/page",true,8191);
    let error=got.unwrap_err().to_string();
    assert!(error.contains("trailing characters"),"{error}");
    println!("ERROR json-trailing {error}");
    print("json-trailing",count);
}

#[test]
fn utf8_codepoint_crosses_both_native_reservation_reads() {
    let (page,mut bytes)=wire(2_000,false);
    let marker=bytes.windows(14).position(|x|x==b"\"timestamp_ms\"").unwrap();
    let mut insert=br#""x":""#.to_vec();
    let prefix=262144;
    let nonsplit=prefix-2;
    insert.resize(nonsplit-marker,b'a');
    insert.extend_from_slice("🚀".as_bytes());
    insert.extend_from_slice(br#"","#);
    bytes.splice(marker..marker,insert);
    let size=bytes.len();
    assert_eq!(size.next_power_of_two()/2,prefix);
    assert_eq!(&bytes[nonsplit..prefix+2], "🚀".as_bytes());
    let (got,count)=read_http(bytes,Framing::Explicit(size),200,"application/json","/history/page",true,1131);
    assert_page(&page,&got.unwrap());
    print("split-utf8",count);
}
