use super::replies::{Part,Replies};
use crate::{carrier::*,declarative::{manifest,protocol::{Content,SurfaceKind}},
    transcript::Transcript,ui::extensions::declarative::{content::ContentView,runtime_probe::{Capture,Runtime}}};
use proteus_contracts::app_protocol::AppTranscriptMessage;
use serde_json::{Value,json};
use std::{collections::HashSet,fs,io::Write,rc::Rc,sync::Arc};

const ROW_BYTES:usize=52*1024;
fn text(n:usize)->String{
    let mut text=format!("Row {n:02}: line\nα😀 transliteration \r\n quote \" backslash \\ nul\0 \t\n");
    text.push_str(&"x".repeat(ROW_BYTES-text.len()));
    assert_eq!(text.len(),ROW_BYTES);
    text
}
fn dto(id:u128,n:usize,user:bool)->AppTranscriptMessage{
    AppTranscriptMessage{
        timestamp_ms:Some(n as i64),message_id:Some(uuid::Uuid::from_u128(id)),phase:None,
        role:if user {"user"}else{"assistant"}.into(),text:text(n),images:vec![],
        tool:None,subagent:None,streaming:false,
    }
}
fn reset(transcript:&mut Transcript,rows:Vec<AppTranscriptMessage>){
    let bytes=serde_json::to_vec(&rows).unwrap();
    transcript.reset(serde_json::from_slice(&bytes).unwrap());
}
fn reply(replies:&mut Replies,key:u64,src:&Arc<str>,user:bool,cx:&mut Context<Chat>)->Entity<ContentView>{
    let wire=if user{"text/plain"}else{"text/markdown"};
    let Part::Content(view)=replies.part(key,wire,src,WeakEntity::default(),ChatKey,user,&mut Window,cx) else {
        panic!("fixture must use a real installed body contributor");
    };
    view
}
fn frame(capture:&Capture,i:usize)->Value{
    let frames=capture.frames.borrow();
    let bytes=&frames[i];
    assert_eq!(bytes.last(),Some(&b'\n'));
    assert_eq!(bytes.iter().filter(|b|**b==b'\n').count(),1);
    serde_json::from_slice(bytes).unwrap()
}
fn save(capture:&Capture,wire:&mut impl Write){
    for bytes in capture.frames.borrow().iter() {wire.write_all(bytes).unwrap();}
}
fn assert_sources(view:&ContentView,text:&Arc<str>,i:usize,candidate:bool){
    let current=view.content.source.as_str();
    let runtime=view.runtime_content();
    assert!(Arc::ptr_eq(&view.content,&runtime));
    assert_eq!(current,text.as_ref());
    assert_eq!(current.as_ptr()==text.as_ptr(),candidate);
    let capture=view.capture();
    let sent=capture.payloads.borrow();
    assert_eq!(sent[i].1,current.len());
    assert_eq!(sent[i].0==current.as_ptr() as usize,candidate);
}
fn resident(cx:&mut Context<Chat>,candidate:bool,wire:&mut impl Write){
    let mut transcript=Transcript::default();
    reset(&mut transcript,(0..40).map(|n|dto(100+n as u128,n,n%2==0)).collect());
    let mut replies=Replies::default();
    let mut retained=Vec::new();
    for (n,row) in transcript.entries().iter().enumerate() {
        let view=reply(&mut replies,row.key,&row.text,n%2==0,cx);
        {
            let v=view.0.borrow();
            assert_sources(&v,&row.text,0,candidate);
            let frame=frame(&v.capture(),0);
            assert_eq!(frame["content"]["language"],if n%2==0{"text/plain"}else{"text/markdown"});
            assert_eq!(frame["content"]["source"],row.text.as_ref());
            assert_eq!(frame["content"]["source_revision"],0);
            assert_eq!(frame["content"]["context"]["theme"],json!({"palette":"initial","ink":"#fff"}));
            assert_eq!(frame["session_dir"],if n%2==0{Value::Null}else{json!("/synthetic/chat")});
            assert_eq!(v.host.ext,"markdown-render");
            assert_eq!(v.raw().as_ref(),row.text.as_ref());
            save(&v.capture(),wire);
        }
        retained.push(view);
    }
    // All 40 source owners are live simultaneously.
    let transcript_ptrs:HashSet<_>=transcript.entries().iter().map(|r|r.text.as_ptr()).collect();
    let sources:HashSet<_>=retained.iter().map(|v|v.0.borrow().content.source.as_str().as_ptr()).collect();
    assert_eq!(sources.len(),40);
    let duplicate=sources.difference(&transcript_ptrs).count();
    let themed = retained.iter().filter(|view| {
        let view=view.0.borrow();
        let capture=view.capture();
        let duplicate=capture.payloads.borrow()[0].0!=view.content.source.as_str().as_ptr() as usize;
        duplicate
    }).count();
    assert_eq!(duplicate,if candidate{0}else{40});
    assert_eq!(themed,if candidate{0}else{40});
    eprintln!("WORK resident rows=40 distinct_duplicate_buffers={duplicate} duplicate_source_bytes={} duplicate_themed_source_buffers={themed}",duplicate*ROW_BYTES);
    let count_before=cx.events.borrow().created;
    for (n,row) in transcript.entries().iter().enumerate(){
        let view=reply(&mut replies,row.key,&row.text,n%2==0,cx);
        assert!(Rc::ptr_eq(&view.0,&retained[n].0));
        assert_eq!(view.0.borrow().capture().frames.borrow().len(),1);
    }
    assert_eq!(cx.events.borrow().created,count_before);
    println!("PASS forty mounted typed rows; plain/markdown/theme/wire, raw text and unchanged warm mounts");
    let weak=Rc::downgrade(&retained[0].0);
    drop(retained);
    replies.retain(&HashSet::new());
    assert!(weak.upgrade().is_none());
    println!("PASS mounted reply is released by the existing row keep set");
}
fn evolving(cx:&mut Context<Chat>,candidate:bool,wire:&mut impl Write){
    let mut transcript=Transcript::default();
    reset(&mut transcript,vec![dto(10,0,false)]);
    let mut replies=Replies::default();
    let key=transcript.entries()[0].key;
    let first=transcript.entries()[0].text.clone();
    let old=Arc::downgrade(&first);
    let view=reply(&mut replies,key,&first,false,cx);
    let mut sent_sources = vec![view.0.borrow().content.source.as_str().as_ptr() as usize];
    let first_copy=view.0.borrow().frozen();
    let capture=view.0.borrow().capture();
    let equal:Arc<str>=Arc::from(first.as_ref());
    assert!(!Arc::ptr_eq(&first,&equal));
    let same=reply(&mut replies,key,&equal,false,cx);
    assert!(Rc::ptr_eq(&same.0,&view.0));
    assert_eq!(same.0.borrow().content.source_revision,Some(0));
    assert_eq!(capture.frames.borrow().len(),1);
    assert_eq!(same.0.borrow().content.source.as_str().as_ptr()==first.as_ptr(),candidate);
    assert_ne!(same.0.borrow().content.source.as_str().as_ptr(),equal.as_ptr());
    drop(equal);
    drop(first);

    // Every accepted replacement keeps its real row key while the queue stays busy.
    for revision in 1..=32 {
        let previous=Arc::downgrade(&transcript.entries()[0].text);
        reset(&mut transcript,vec![dto(10,revision,false)]);
        let row=&transcript.entries()[0];
        assert_eq!(row.key,key);
        let again=reply(&mut replies,key,&row.text,false,cx);
        let v=again.0.borrow();
        assert_eq!(v.content.source_revision,Some(revision as u64));
        assert_eq!(v.content.source.as_str(),row.text.as_ref());
        assert_eq!(v.content.source.as_str().as_ptr()==row.text.as_ptr(),candidate);
        assert!(Arc::ptr_eq(&v.content,&v.runtime_content()));
        assert_eq!(capture.frames.borrow().len(),1);
        if revision>1 { assert!(previous.upgrade().is_none(),"obsolete revision {revision} source"); }
    }
    assert_eq!(first_copy().as_ref(),text(0));
    assert_eq!(old.upgrade().is_some(),candidate);
    drop(first_copy);
    assert!(old.upgrade().is_none());
    let current=transcript.entries()[0].text.clone();
    *cx.theme.borrow_mut()=json!({"palette":"while-pending","ink":"#ddeeff"});
    view.0.borrow().ack(Some(5),cx);
    assert_eq!(capture.frames.borrow().len(),1);
    view.0.borrow().ack(Some(0),cx);
    assert_eq!(capture.frames.borrow().len(),2);
    let admitted=frame(&capture,1);
    assert_eq!(admitted["content"]["source"],current.as_ref());
    assert_eq!(admitted["content"]["source_revision"],32);
    assert_eq!(admitted["content"]["context"]["theme"]["palette"],"while-pending");
    assert_sources(&view.0.borrow(),&current,1,candidate);
    sent_sources.push(view.0.borrow().content.source.as_str().as_ptr() as usize);

    // Same source but newly enabled contributor context should advance once.
    cx.prefs().set_enabled("mermaid-render",false);
    let rerender=reply(&mut replies,key,&current,false,cx);
    assert!(Rc::ptr_eq(&view.0,&rerender.0));
    assert_eq!(rerender.0.borrow().content.source_revision,Some(33));
    assert_eq!(capture.frames.borrow().len(),2);
    view.0.borrow().ack(Some(0),cx);
    assert_eq!(capture.frames.borrow().len(),2);
    view.0.borrow().ack(Some(32),cx);
    assert_eq!(capture.frames.borrow().len(),3);
    let contextual=frame(&capture,2);
    assert_eq!(contextual["content"]["source_revision"],33);
    assert_eq!(contextual["content"]["source"],current.as_ref());
    assert!(contextual["content"]["context"]["contributors"].get("mermaid").is_none());
    assert_sources(&view.0.borrow(),&current,2,candidate);
    sent_sources.extend(std::iter::repeat_n(view.0.borrow().content.source.as_str().as_ptr() as usize,3));

    // Invalidation while busy must admit another render of the same revision after ACK.
    *cx.theme.borrow_mut()=json!({"palette":"new-theme","ink":"#abc"});
    view.0.borrow().draw(cx);
    assert_eq!(capture.frames.borrow().len(),3);
    view.0.borrow().ack(None,cx);
    assert_eq!(capture.frames.borrow().len(),3);
    view.0.borrow().ack(Some(33),cx);
    assert_eq!(capture.frames.borrow().len(),4);
    assert_eq!(frame(&capture,3)["content"]["source_revision"],33);
    assert_eq!(frame(&capture,3)["content"]["context"]["theme"]["palette"],"new-theme");
    view.0.borrow().restart(cx);
    assert_eq!(capture.frames.borrow().len(),5);
    assert_eq!(frame(&capture,4),frame(&capture,3));
    assert_sources(&view.0.borrow(),&current,4,candidate);
    assert_eq!(view.0.borrow().raw().as_ref(),current.as_ref());
    assert!(capture.errors.borrow().is_empty());
    save(&capture,wire);
    let dup = capture.payloads.borrow().iter().zip(&sent_sources).filter(|(seen, retained)|seen.0 != **retained).count();
    assert_eq!(sent_sources.len(),capture.payloads.borrow().len());
    assert_eq!(dup,if candidate{0}else{5});
    eprintln!("WORK evolving initial_and_replacements=33 admitted_with_controls=5 duplicate_themed_source_buffers={dup}");
    println!("PASS equal bytes/different Arc no-op, full source changes, old captured fallback, rapid pending and eventual latest, theme invalidation/context/restart");
}
fn owned_controls(cx:&Context<Chat>,wire:&mut impl Write){
    let src=String::from("nested source λ \n🎉");
    let original=src.as_ptr();
    let body=Content{
        language:"json-render".into(),source:src.into(),
        context:json!([4,"opaque invalid for Render context"]),source_revision:None,
    };
    assert_eq!(body.source.as_str().as_ptr(),original);
    let snapshot=Arc::new(body);
    let mut runtime=Runtime::new("nested",SurfaceKind::Content,Some(snapshot.clone()),false);
    runtime.draw("nested",cx);
    let capture=runtime.capture.clone();
    assert_eq!(capture.frames.borrow().len(),1);
    let payload=frame(&capture,0);
    assert_eq!(payload["content"]["source"],snapshot.source.as_str());
    assert!(payload["content"].get("source_revision").is_none());
    assert_eq!(payload["content"]["context"].as_object().unwrap().len(),1);
    assert_eq!(payload["content"]["context"]["theme"],*cx.theme.borrow());
    assert_ne!(capture.payloads.borrow()[0].0,original as usize);
    assert_eq!(snapshot.context,json!([4,"opaque invalid for Render context"]));
    save(&capture,wire);

    let mut preview=Runtime::new("preview",SurfaceKind::Preview,None,false);
    preview.draw("preview",cx);
    let p=frame(&preview.capture,0);
    assert_eq!(p["content"]["language"],"");
    assert_eq!(p["content"]["source"],"");
    assert!(p["content"].get("source_revision").is_none());
    assert_eq!(p["content"]["context"]["only_preview"],"visual fixture");
    save(&preview.capture,wire);
    println!("PASS independently owned nested String buffer, exact themed context normalization, empty preview and absent revision");
}
pub(crate) fn run(candidate:bool){
    let bundle=manifest::bundled_root();
    assert_eq!(bundle,std::env::current_dir().unwrap().join("bundled"));
    assert_eq!(crate::preferences::config_dir().unwrap(),std::env::current_dir().unwrap().join("config/fixture-r84"));
    let (found,errors)=manifest::discover_sources(&bundle,None);
    assert!(errors.is_empty(),"{errors:?}");
    assert_eq!(found.len(),3);
    let mut cx=Context::default();
    *cx.theme.borrow_mut()=json!({"palette":"initial","ink":"#fff"});
    let mut wire=fs::File::create("frames.jsonl").unwrap();
    resident(&mut cx,candidate,&mut wire);
    evolving(&mut cx,candidate,&mut wire);
    owned_controls(&cx,&mut wire);
    wire.sync_all().unwrap();
    eprintln!("WORK shape content_inline_value_bytes={}",std::mem::size_of::<Content>());
    println!("PASS bounded fixture; exact outgoing bytes emitted only in scratch");
}
