use super::*;
use crate::{fixture::{rows,cursor}, meter::measure};
use std::{fmt::{self,Write},path::PathBuf};
use serde_json::{Value,json};

fn repr(k: Option<&Key>)->Value {
    k.map(|k|json!({"identity":k.identity,"revision":k.revision,"layout":k.layout,"prefix":k.prefix,"base":k.base})).unwrap_or(Value::Null)
}
fn path_cases()->Vec<(&'static str,ChatKey)> {
    let mut v = vec![
        ("path",ChatKey::Proteus("/synthetic/saved-chat".into())),
        ("empty_path",ChatKey::Proteus("".into())), ("relative",ChatKey::Proteus("relative//./../a:b/".into())),
        ("unicode",ChatKey::Proteus("кат/日本/🙂\n".into())),
        ("long",ChatKey::Proteus("x".repeat(4096).into())),
        ("codex",ChatKey::Codex("opaque::child:\nλ".into())), ("codex_empty",ChatKey::Codex(String::new())),
        ("codex_long",ChatKey::Codex(":a".repeat(2048))),
    ];
    for (name,n) in [("sha55",55),("sha56",56),("sha63",63),("sha64",64),("sha65",65)] {
        // 5 bytes of namespace and 37 bytes of colon + UUID in each durable preimage.
        v.push((name,ChatKey::Proteus("q".repeat(n-42).into())));
    }
    #[cfg(unix)] {
        use std::os::unix::ffi::OsStringExt;
        v.push(("non_utf8", ChatKey::Proteus(std::ffi::OsString::from_vec(b"a/\xff:\xe2\x82/\x80\n".to_vec()).into())));
    }
    v
}

struct Reject { seen:Vec<String> }
impl Write for Reject { fn write_str(&mut self,s:&str)->fmt::Result {self.seen.push(s.to_owned()); Err(fmt::Error)} }

#[test]
fn all_key_fields_and_key_window(){
    for (name,chat_key) in path_cases(){
        let owned=chat_key.tab_id();
        let expected_str = match &chat_key { ChatKey::Proteus(p)=>format!("chat:{}",p.to_string_lossy()), ChatKey::Codex(s)=>format!("codex:{s}") };
        assert_eq!(owned,expected_str);
        let public=proteus_tabs::chat_key(&owned).unwrap();
        assert_eq!(public.tab_id(),owned); assert_eq!(format!("{chat_key}"),owned);
        let mut reject=Reject { seen:vec![] }; assert!(write!(&mut reject,"{chat_key}").is_err());
        assert_eq!(reject.seen,vec![owned.clone()]);
        let mut session=Session::new(PathBuf::from("wrong-root-dir"));
        session.key=chat_key;
        let mut cur=cursor("новая:ревизия\n",0);
        cur.base=Some(AppTranscriptBase {revision:"prior:".into(),common_prefix:0});
        let (unknown,cost)=measure(||height_key::key(std::hint::black_box(&session),std::hint::black_box(&cur)));
        assert!(unknown.is_none());
        assert_eq!((cost.requests,cost.bytes),(0,0));
        for (index,id) in [Uuid::nil(),Uuid::from_u128(0xabcd1234),Uuid::max(),Uuid::from_u128(42)].into_iter().enumerate() {
            cur.before=index; if index==2 {cur.base=None;} if index==3 {cur.base=Some(AppTranscriptBase { revision:String::new(),common_prefix:index });}
            if let Some(base)=&mut cur.base {base.common_prefix=index;}
            session.snapshot_identity=Some((id,"ignored-stream".into()));
            let (k,cost)=measure(||height_key::key(std::hint::black_box(&session),std::hint::black_box(&cur)));
            let k=k.unwrap();
            assert_eq!(k.identity,scroller::height_hash(format!("{owned}:{id}")));
            assert_eq!(k.revision,scroller::height_hash(&cur.revision));assert_eq!(k.layout,[0;32]);
            assert_eq!(k.prefix,cur.before.saturating_sub(1));
            assert_eq!(k.base,cur.base.as_ref().map(|b|(scroller::height_hash(&b.revision),b.common_prefix.saturating_sub(1))));
            println!("CASE {}",json!({"case":name,"idx":index,"tab":owned,"id":id,"key":repr(Some(&k)),
                "public_capacity":owned.capacity(),"requests":cost.requests,"bytes":cost.bytes}));
        }
    }
    for id in ["",":","chat","codex","CHAT:first","file:target"] { assert!(proteus_tabs::chat_key(id).is_none()); }
    for n in 0..=33 {
        let raw="x".repeat(n);let (id,cost)=measure(||ChatKey::Codex(raw).tab_id());
        println!("PUBLIC {}",json!([n,id.capacity(),cost.requests,cost.bytes]));
    }
}

fn evt(id:Uuid,stream:&str,seq:u64,root:Option<Uuid>,cur:Option<AppTranscriptCursor>) -> AppServerEvent {
    AppServerEvent::SessionSnapshot {snapshot:Box::new(AppSessionSnapshot {
        session_id:id, stream_id:stream.into(),seq,root_thread_id:root,
        transcript:rows(0,50),history:cur,execution:Default::default(),
    })}
}

fn step(chat:&mut Chat,cx:&mut Context<Chat>,tag:&str,event:AppServerEvent,accepted:bool,depth:usize,expect:Option<&Key>) {
    cx.calls.clear();
    let (shown,cost)=measure(||chat.apply_event(std::hint::black_box(event),cx));
    assert_eq!(shown,accepted,"{tag}");
    let actual=cx.calls.iter().filter_map(|c| if let Call::Bind(k)=c{Some(k)}else{None}).collect::<Vec<_>>();
    assert_eq!(actual.len(),depth,"{tag}");
    for k in &actual {assert_eq!(k.as_ref(),expect,"{tag}")}
    if !accepted { assert_eq!((cost.requests,cost.bytes),(0,0)); assert!(cx.calls.is_empty()); }
    println!("ROUTE {}",json!({"case":tag,"shown":shown,"keys":actual.iter().map(|k|repr(k.as_ref())).collect::<Vec<_>>(),
        "calls":format!("{:?}",cx.calls),"requests":cost.requests,"bytes":cost.bytes}));
}

#[test]
fn accepted_snapshot_to_scroller_and_rejects(){
    let mut chat=Chat::new("relative//./../chat:а".into());
    let mut cx=Context::default();
    cx.calls.reserve(100);
    let (id,other)=(Uuid::from_u128(0xabcdef),Uuid::from_u128(99));
    let c=cursor("revision:α",25);
    let key_for=|id:Uuid,c:&AppTranscriptCursor| Key{
        identity:scroller::height_hash(format!("chat:relative//./../chat:а:{id}")),
        revision:scroller::height_hash(&c.revision),layout:[0;32],prefix:c.before.saturating_sub(1),
        base:c.base.as_ref().map(|b|(scroller::height_hash(&b.revision),b.common_prefix.saturating_sub(1)))
    };
    // Exercise the unchanged optional durable-id guard through the range caller itself.
    chat.history.cursor=Some(c.clone());
    let (_,unknown_cost)=measure(||chat.sync_history_range(&mut cx));
    assert_eq!(cx.calls.iter().filter(|x|matches!(x,Call::Bind(None))).count(),1);
    assert_eq!(unknown_cost.requests,0);
    chat.history=Default::default();
    chat.session.cursor.begin_connection();
    step(&mut chat,&mut cx,"first",evt(id,"A",3,None,Some(c.clone())),true,2,Some(&key_for(id,&c)));
    step(&mut chat,&mut cx,"duplicate",evt(id,"A",3,None,Some(c.clone())),false,0,None);
    step(&mut chat,&mut cx,"stale",evt(id,"A",2,None,Some(c.clone())),false,0,None);
    step(&mut chat,&mut cx,"foreign-session",evt(other,"A",4,None,Some(c.clone())),false,0,None);
    step(&mut chat,&mut cx,"foreign-stream",evt(id,"B",4,None,Some(c.clone())),false,0,None);
    let mut next=cursor("rev:β",0);next.base=Some(AppTranscriptBase{revision:c.revision.clone(),common_prefix:0});
    step(&mut chat,&mut cx,"new-revision",evt(id,"A",4,Some(Uuid::max()),Some(next.clone())),true,2,Some(&key_for(id,&next)));
    chat.session.cursor.begin_connection();
    step(&mut chat,&mut cx,"reopen",evt(id,"B",0,None,Some(next.clone())),true,2,Some(&key_for(id,&next)));
    step(&mut chat,&mut cx,"root-reappears",evt(id,"B",1,Some(Uuid::nil()),Some(next.clone())),true,2,Some(&key_for(id,&next)));
    step(&mut chat,&mut cx,"no-cursor",evt(id,"B",2,None,None),true,2,None);
    chat.session.cursor.begin_connection();
    step(&mut chat,&mut cx,"other-accepted",evt(other,"C",0,None,Some(c.clone())),true,2,Some(&key_for(other,&c)));
}
