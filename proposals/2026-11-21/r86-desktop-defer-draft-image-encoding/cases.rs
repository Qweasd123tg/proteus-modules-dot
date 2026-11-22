use super::*;
use crate::attachment_io::{self,Batch,Budget,Source};
use proteus_contracts::domain::{ImageAttachment,ImageRef,MAX_IMAGE_BYTES,MAX_INPUT_IMAGES};
use std::{fs,io::Write,path::PathBuf};

const EXPECTED_MAX_B64:usize=6_990_512;
fn record_wire(out:&mut std::fs::File,request:&Captured) {
    out.write_all(&request.body).unwrap();out.write_all(b"\n").unwrap();
}
fn mount(batch:Batch)->Attachments{
    let mut draft=Attachments::default();
    assert!(batch.errors.is_empty(),"{:?}",batch.errors);
    for p in batch.images{
        let expected=p.bytes.as_ptr() as usize;
        draft.mount(p).unwrap();
        assert_eq!(draft.raw_pointers().last(),Some(&expected));
    }
    draft
}
fn make_file_batch()->Attachments{
    let budget=Budget{slots:MAX_INPUT_IMAGES,bytes:MAX_IMAGE_BYTES};
    let batch=attachment_io::read_batch(
        vec![Source::File("fixtures/large.png".into()),Source::Bytes("pasted.png".into(),fs::read("fixtures/second.png").unwrap())],
        budget
    );
    let draft=mount(batch);
    assert_eq!(draft.remaining().bytes,0);
    assert_eq!(draft.remaining().slots,2);
    draft
}
fn make_sigs(a:&str,b:&str)->Attachments{
    mount(attachment_io::read_batch(
        vec![Source::Bytes(a.into(),b"GIF89a".to_vec()),Source::Bytes(b.into(),b"\xff\xd8\xff".to_vec())],
        Budget{slots:4,bytes:5*1024*1024}))
}
fn base_chat(draft:Attachments,fail:bool)->Chat{
    Chat{
        readonly:None,codex:None,session:Session{feedback:Feedback::default(),dir:"/synthetic/draft".into(),pending:None,connected:true},
        composer:Composer(Input{value:String::new()}),attachments:draft,attachments_loading:false,attachment_generation:0,
        next_request:35,api:Some(Api{wire:Arc::default(),fail}),saved_drafts:vec![],notices:vec![],codex_calls:0,
    }
}
fn snapshots(chat:&Chat)->Arc<Mutex<Vec<Captured>>>{chat.api.as_ref().unwrap().wire.clone()}
fn exec(p:&mut Pending)->anyhow::Result<Value>{p.execute.take().unwrap()()}
fn latest(chat:&Chat)->&crate::feedback::PendingSend{
    chat.session.feedback.latest_receipt().unwrap().0
}
fn echo(name:&str,mime:&str)->ImageRef{
    ImageRef{id:name.into(),name:name.into(),mime_type:mime.into(),path:format!("/synthetic/{name}").into()}
}
fn checks(_candidate:bool){
    let over=attachment_io::prepare("too-large".into(),vec![0;MAX_IMAGE_BYTES+1]).err().unwrap();
    assert_eq!(over,"too-large: image exceeds 5 MiB");
    let unsupported=attachment_io::prepare("unsupported".into(),vec![0;32]).err().unwrap();
    assert_eq!(unsupported,"unsupported: unsupported image format");
    let signatures:&[(&str,&str,&[u8])]=&[
        ("image/png","p.png",b"\x89PNG\r\n\x1a\n"),("image/jpeg","p.jpg",b"\xff\xd8\xff"),
        ("image/gif","p.gif",b"GIF87a"),("image/webp","p.webp",b"RIFF0000WEBP"),
    ];
    let mut draft=mount(attachment_io::read_batch(
        signatures.iter().map(|(_,name,bytes)|Source::Bytes((*name).into(),bytes.to_vec())).collect(),
        Budget{slots:MAX_INPUT_IMAGES,bytes:MAX_IMAGE_BYTES}));
    assert_eq!(draft.remaining().slots,0);
    let extra=attachment_io::prepare("fifth".into(),b"GIF89a".to_vec()).unwrap();
    assert_eq!(draft.mount(extra).unwrap_err(),"fifth: к сообщению можно приложить не больше 4 изображений");
    let capped=attachment_io::read_batch(vec![
        Source::File("fixtures/large.png".into()),
        Source::File("fixtures/not-opened.png".into()),
    ],Budget{slots:1,bytes:4*1024*1024});
    assert_eq!(capped.images.len(),1);
    assert_eq!(capped.errors.len(),1);
    assert!(capped.errors[0].starts_with("Остальные"));
    let mut chat=base_chat(draft,false);
    let wire=snapshots(&chat);
    let mut cx=Context{notes:0};
    let mut window=Window;
    let mut job=chat.stage(&mut window,&mut cx).unwrap();
    assert_eq!(&latest(&chat).images,&["p.png","p.jpg","p.gif","p.webp"]);
    let result=exec(&mut job);
    assert!(result.is_ok());
    let sent=wire.lock().unwrap();
    assert_eq!(sent.len(),1);
    for (a,(mime,name,bytes)) in sent[0].images.iter().zip(signatures){
        assert_eq!(&a.name,name);
        assert_eq!(&a.mime_type,mime);
        assert_eq!(a.decode().unwrap(),*bytes);
    }
    drop(sent);
    chat.finished(job,result,&mut window,&mut cx);
    assert!(chat.attachments.is_empty());
    println!("PASS limits: all four formats/order, size-before-MIME error, no fifth read, no replacement upload");
}
fn retained_and_retry(candidate:bool,out:&mut std::fs::File){
    let draft=make_file_batch();
    let pointers=draft.raw_pointers();
    let (raw,encoded)=draft.backing();
    assert_eq!(raw,MAX_IMAGE_BYTES);
    assert_eq!(encoded,if candidate{0}else{EXPECTED_MAX_B64});
    eprintln!("WORK five_mib_draft raw_bytes={raw} retained_base64_bytes={encoded}");
    let mut chat=base_chat(draft,true);
    let wire=snapshots(&chat);
    let mut cx=Context{notes:0};
    let mut window=Window;
    chat.composer.0.value=" \t original draft \n ".to_owned();
    let mut job=chat.stage(&mut window,&mut cx).unwrap();
    assert!(chat.attachments.is_empty());
    assert_eq!(job.draft.raw_pointers(),pointers);
    assert!(wire.lock().unwrap().is_empty()); // worker not executed
    assert_eq!(latest(&chat).text,"original draft");
    assert_eq!(&latest(&chat).images,&["large.png","pasted.png"]);
    let rejected=exec(&mut job);
    assert!(rejected.is_err());
    chat.composer.0.value="new text after the send".into();
    chat.finished(job,rejected,&mut window,&mut cx);
    assert_eq!(chat.saved_drafts.len(),1);
    assert_eq!(chat.saved_drafts[0].attachments.raw_pointers(),pointers);
    assert_eq!(chat.saved_drafts[0].attachments.backing(),(raw,encoded));
    assert_eq!(chat.saved_drafts[0].text," \t original draft \n ");
    assert_eq!(chat.composer.0.value,"new text after the send");
    assert!(chat.notices[0].contains("fixture refuses"));
    eprintln!("WORK five_mib_preserved_failed_draft raw_bytes={raw} retained_base64_bytes={encoded}");
    let id=chat.saved_drafts[0].id.clone();
    chat.restore_draft(&id,&mut window,&mut cx);
    assert_eq!(chat.attachments.raw_pointers(),pointers);
    assert_eq!(chat.composer.0.value," \t original draft \n ");
    assert_eq!(chat.saved_drafts[0].text,"new text after the send");

    // Retry uses the same immutable admitted bytes, not a new read from the changed file.
    let original=fs::read("fixtures/large.png").unwrap();
    fs::write("fixtures/large.png",b"changed after the draft was captured").unwrap();
    chat.api.as_mut().unwrap().fail=false;
    let mut retry=chat.stage(&mut window,&mut cx).unwrap();
    let accepted=exec(&mut retry);
    fs::write("fixtures/large.png",&original).unwrap();
    assert!(accepted.is_ok());
    {
        let sent=wire.lock().unwrap();
        assert_eq!(sent.len(),2);
        assert_eq!(sent[0].text,"original draft");
        assert_eq!(sent[0].session_dir.to_str(),Some("/synthetic/draft"));
        assert_ne!(sent[0].id,sent[1].id);
        assert_eq!(sent[0].images,sent[1].images);
        assert_eq!(sent[1].images[0].decode().unwrap(),original);
        assert_eq!(sent[1].images[1].decode().unwrap(),fs::read("fixtures/second.png").unwrap());
        assert_eq!(sent[1].images.iter().map(|a|a.data.len()).sum::<usize>(),EXPECTED_MAX_B64);
        for request in sent.iter(){record_wire(out,request);}
    }
    chat.finished(retry,accepted,&mut window,&mut cx);
    assert_eq!(latest(&chat).status(),"Отправлено");
    chat.session.feedback.submitted("original draft",&[echo("large.png","image/png"),echo("pasted.png","image/png")]);
    assert_eq!(chat.session.feedback.visible_sends().count(),0);
    println!("PASS full-sized draft pointer/size, refusal saved beside new text, retry identical decoded original payload");
}
fn echo_order(_candidate:bool,out:&mut std::fs::File){
    let mut chat=base_chat(make_sigs("first.gif","second.jpg"),true);
    let wire=snapshots(&chat);
    let mut cx=Context{notes:0};
    let mut window=Window;
    let mut job_a=chat.stage(&mut window,&mut cx).unwrap();
    chat.attachments=make_sigs("second.gif","first.jpg");
    let mut job_b=chat.stage(&mut window,&mut cx).unwrap();
    let first=job_a.id.clone();
    let second=job_b.id.clone();
    assert_ne!(first,second);
    assert_eq!(chat.session.feedback.visible_sends().count(),2);
    chat.session.feedback.submitted("",&[echo("second.gif","image/gif"),echo("first.jpg","image/jpeg")]);
    assert_eq!(latest(&chat).id,first);
    let failure_b=exec(&mut job_b);
    chat.finished(job_b,failure_b,&mut window,&mut cx);
    assert!(chat.attachments.is_empty() && chat.saved_drafts.is_empty());
    assert!(chat.notices.is_empty());
    let failure_a=exec(&mut job_a);
    chat.finished(job_a,failure_a,&mut window,&mut cx);
    assert_eq!(chat.attachments.len(),2);
    assert_eq!(chat.session.feedback.visible_sends().count(),0);
    assert_eq!(chat.notices.len(),1);
    for request in wire.lock().unwrap().iter(){record_wire(out,request);}
    println!("PASS image-only ordered receipt names; observed error suppresses duplicate restore, unobserved error restores raw draft");
}
fn guards(){
    let mut chat=base_chat(Attachments::default(),false);
    let mut cx=Context{notes:0};
    let mut window=Window;
    assert!(chat.stage(&mut window,&mut cx).is_none());
    chat.attachments=make_sigs("one.gif","two.jpg");
    chat.readonly=Some(());
    assert!(chat.stage(&mut window,&mut cx).is_none());
    chat.readonly=None;
    chat.codex=Some(());
    assert!(chat.stage(&mut window,&mut cx).is_none() && chat.codex_calls==1);
    chat.codex=None;
    chat.attachments_loading=true;
    assert!(chat.stage(&mut window,&mut cx).is_none());
    chat.attachments_loading=false;
    chat.session.connected=false;
    assert!(chat.stage(&mut window,&mut cx).is_none());
    assert_eq!(chat.attachments.len(),2);
    assert_eq!(chat.attachment_generation,0);
    assert_eq!(chat.session.feedback.visible_sends().count(),0);
    assert!(snapshots(&chat).lock().unwrap().is_empty());
    println!("PASS empty/loading/disconnected/readonly/Codex admission boundaries");
}
pub fn run(candidate:bool){
    let mut out=std::fs::File::create("exact-send-requests.jsonl").unwrap();
    checks(candidate);
    retained_and_retry(candidate,&mut out);
    echo_order(candidate,&mut out);
    guards();
    out.sync_all().unwrap();
}
