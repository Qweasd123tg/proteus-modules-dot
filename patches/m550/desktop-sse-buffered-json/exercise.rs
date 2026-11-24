use super::*;
use crate::meter::measure;
use proteus_contracts::app_protocol::{AppSessionSnapshot,AppTranscriptBase,AppTranscriptCursor,AppTranscriptMessage};
use std::hash::{Hash,Hasher,DefaultHasher};
use std::io::{self,Cursor,Read};

fn output(event:AppServerEvent) -> StdioOutput {
    StdioOutput::Event{event:Box::new(event)}
}
fn event(kind:&str) -> Bytes {
    encode_sse_output(&output(if kind=="catalog" {AppServerEvent::SessionCatalogUpdated} else {AppServerEvent::Shutdown}))
}
fn snapshot(multiline_bytes:usize) -> Bytes {
    let sid="a800244b-0da4-408f-a92e-faa35c05a802".parse().unwrap();
    let transcript=(0..50).map(|i|AppTranscriptMessage{
        message_id:(i%8==0).then(||format!("a800244b-0da4-408f-a92e-{i:012x}").parse().unwrap()), timestamp_ms:Some(i), phase:None,
        role:if i%2==0{"user"}else{"assistant"}.into(),
        text:format!("стр:{i}\n{}","🦀".repeat(multiline_bytes/4)),
        images:vec![], tool:None, subagent:None, streaming:false,
    }).collect();
    let history=Some(AppTranscriptCursor{revision:"rev-a".into(),before:49950,
        base:Some(AppTranscriptBase{revision:"older".into(),common_prefix:49000})});
    encode_sse_output(&output(AppServerEvent::SessionSnapshot{snapshot:Box::new(AppSessionSnapshot {
        session_id:sid,stream_id:"live-incarnation".into(),seq:2,root_thread_id:None,
        transcript,history,execution:Default::default(),
    })}))
}
fn open(input: Vec<u8>, cap:usize, read_at_most:usize, noisy:bool)->EventStream {
    EventStream{reader:BufReader::with_capacity(cap,Box::new(Split{
        data:Cursor::new(input), bound:read_at_most, reads:0, noisy
    }))}
}
struct Split { data:Cursor<Vec<u8>>,bound:usize,reads:usize,noisy:bool }
impl Read for Split {
    fn read(&mut self, b:&mut[u8])->io::Result<usize>{
        self.reads+=1;
        if self.noisy && self.reads%7==3 {
            return Err(io::Error::new(io::ErrorKind::Interrupted,"synthetic interrupted read"));
        }
        let n=self.bound.min(b.len());self.data.read(&mut b[..n])
    }
}
fn heartbeat(x:Option<Result<StreamItem>>) {assert!(matches!(x,Some(Ok(StreamItem::Heartbeat))));}
fn item(actual:Option<Result<StreamItem>>) -> String {
    match actual {
        Some(Ok(StreamItem::Event(e)))=>serde_json::to_string(&e).unwrap(),
        Some(Ok(StreamItem::Heartbeat))=>"heartbeat".into(),
        Some(Err(e))=>format!("err::{e:#}"),
        None=>"eof".into(),
    }
}
fn assert_page(m:Option<Result<StreamItem>>, body_size:usize){
    let Some(Ok(StreamItem::Event(e)))=m else {panic!("expected snapshot output");};
    let AppServerEvent::SessionSnapshot{snapshot}=*e else {panic!("wrong event");};
    let c=snapshot.history.as_ref().unwrap();
    assert_eq!((c.before,c.revision.as_str(),c.base.as_ref().unwrap().common_prefix),(49950,"rev-a",49000));
    assert_eq!(snapshot.seq,2);
    assert_eq!(snapshot.root_thread_id,None);
    assert_eq!(snapshot.transcript.len(),50);
    for (i,m) in snapshot.transcript.iter().enumerate(){
        assert_eq!(m.text,format!("стр:{i}\n{}","🦀".repeat(body_size/4)));
        assert_eq!(m.role,if i%2==0{"user"}else{"assistant"});
        assert_eq!(m.timestamp_ms,Some(i as i64));
    }
}

#[test]
fn canonical_first_page_and_large_fallback() {
    for (mode,entry_bytes) in [("buffered-50",0),("fragmented-50",4096)] {
        let frame=snapshot(entry_bytes);
        assert_eq!(frame.len()<8192,entry_bytes==0);
        // Same Core keepalive convention that primes the reader at startup.
        let mut body=b": connected\n\n".to_vec();body.extend_from_slice(&frame);
        body.extend_from_slice(&event("catalog"));body.extend_from_slice(&event("shutdown"));
        let first_chunk=if entry_bytes==0 {b": connected\n\n".len()+frame.len()} else {usize::MAX};
        if entry_bytes==0 {assert!(first_chunk<=8192);}
        let mut stream=open(body,8192,first_chunk,false);
        heartbeat(stream.next());
        let (decoded,mem)=measure(||stream.next());
        assert_page(decoded,entry_bytes);
        assert_eq!(item(stream.next()),r#"{"type":"session_catalog_updated"}"#);
        assert_eq!(item(stream.next()),r#"{"type":"shutdown"}"#);
        assert_eq!(item(stream.next()),"eof");
        println!("ALLOC {mode} {} {} {}",frame.len(),mem.requests,mem.bytes);
    }
}

#[test]
fn boundaries_broken_and_noncanonical() {
    let cases=[
        ("plain", b"event: output\ndata: {\"type\":\"event\",\"event\":{\"type\":\"shutdown\"}}\n\n".as_slice(), "shutdown"),
        ("noheader", b"data: {\"type\":\"event\",\"event\":{\"type\":\"shutdown\"}}\n\n", "shutdown"),
        ("no-space",b"data:{\"type\":\"event\",\"event\":{\"type\":\"shutdown\"}}\n\n","shutdown"),
        ("crlf", b"event: output\r\ndata: {\"type\":\"event\",\"event\":{\"type\":\"shutdown\"}}\r\n\r\n", "shutdown"),
        ("cr-left", b"event: output\ndata: {\"type\":\"event\",\"event\":{\"type\":\"shutdown\"}}\r\r\n\n","shutdown"),
        ("multi", b"event: output\ndata: {\"type\":\"event\",\n: hidden comment\ndata: \"event\":{\"type\":\"shutdown\"}}\n\n","shutdown"),
        ("empty-data", b"data: \r\n\ndata: {\"type\":\"event\",\"event\":{\"type\":\"shutdown\"}}\n\n","shutdown"),
        ("response", b"event: output\ndata: {\"type\":\"response\",\"id\":null,\"ok\":false,\"output\":null,\"error\":\"fixture\"}\n\n","err::event stream failed: fixture"),
        ("response-none", b"event: output\ndata: {\"type\":\"response\",\"id\":null,\"ok\":true,\"output\":null,\"error\":null}\n\n","err::unexpected response on the event stream"),
        ("invalid-json", b"event: output\ndata: nope\n\n","err::expected ident"),
        ("malformed-utf8", b"event: output\ndata: \xff\n\n","err::stream did not contain valid UTF-8"),
        ("unknown",b"id: unrelated\ndata: {\"type\":\"event\",\"event\":{\"type\":\"shutdown\"}}\n\n","shutdown"),
    ];
    let mut fingerprints=DefaultHasher::new();
    let mut runs=0;
    for (label,payload,expect) in cases {
        for capacity in [1,2,5,11,22,32,76,128,8192] {
            for bound in [1,3,13,65,usize::MAX] {
                let tail=event("catalog");
                let b=[b": connected\n\n".as_slice(),payload,tail.as_ref()].concat();
                let mut reader=open(b,capacity,bound,true);
                heartbeat(reader.next());
                let first=item(reader.next());
                if expect=="shutdown" {assert_eq!(first,r#"{"type":"shutdown"}"#,"{label} {capacity} {bound}");}
                else {assert!(first.starts_with(expect),"{label} {capacity} {bound} {first:?}");}
                let second=item(reader.next());
                assert_eq!(second,r#"{"type":"session_catalog_updated"}"#,"{label} {capacity} {bound}");
                assert_eq!(item(reader.next()),"eof");
                (label,capacity,bound,first,second).hash(&mut fingerprints);
                runs+=1;
            }
        }
    }
    for payload in [b"event: output\ndata: nope".as_slice(),b"event: output\ndata: nope\n"] {
        let mut reader=open(payload.to_vec(),8192,usize::MAX,false);
        assert_eq!(item(reader.next()),"eof");
        runs+=1;
    }
    let mut standalone_cr=open(b"event: output\ndata: nope\n\r".to_vec(),8192,usize::MAX,false);
    assert!(item(standalone_cr.next()).starts_with("err::expected ident"));
    println!("PARITY {} {}",runs+1,fingerprints.finish());
}
