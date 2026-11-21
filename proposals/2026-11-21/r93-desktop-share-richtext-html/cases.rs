use declarative::protocol::{parse,Incoming};

fn rich(id:&str, html:&str, slots:Option<Value>)->Value {
    let mut root=json!({"type":"rich_text","id":id,"html":html});
    if let Some(slots)=slots {root["inlines"]=slots;}
    root
}
fn line(root:Value, target:&str)->String {
    json!({"type":"view","view":target,"session_dir":"/example/session","root":root,
        "sequence":73,"source_revision":97}).to_string()
}
fn root(root:Value)->Node {
    let frame=line(root,"panel");
    let message=std::thread::spawn(move||parse(&frame).unwrap()).join().unwrap();
    match message {
        Incoming::View {root,sequence:73,source_revision:Some(97),..}=>root,
        _=>panic!("expected exact View envelope"),
    }
}
fn html(root:&Node)->&str{
    let Node::RichText {html,..}=root else {panic!("expected leaf")};
    html.as_str()
}
fn adopt(node:Node, view:&mut DeclarativeView, app:&App){
    view.root=Some(Rc::new(node));
    view.prepare_root(&mut Window,&mut Context::fixture(app));
}
fn wire_shape() {
    assert!(html(&root(rich("empty","",None))).is_empty());
    let language="<p>quotes \" élève, луна &amp; 🚀</p>\r\n";
    assert_eq!(html(&root(rich("unicode",language,None))),language);
    let mut missing=rich("id","",None);
    missing.as_object_mut().unwrap().remove("html");
    let mut unknown=rich("id","",None);
    unknown["typo"]=json!(true);
    let mut null=rich("id","",None); null["html"]=Value::Null;
    let mut array=rich("id","",None); array["html"]=json!(["x"]);
    let mut number=rich("id","",None); number["html"]=json!(123);
    let duplicate=line(rich("id","",None),"content:demo").replace("\"html\":\"\"","\"html\":\"\",\"html\":\"x\"");
    for frame in [line(missing,"content:demo"),line(null,"content:demo"),line(array,"content:demo"),
        line(number,"content:demo"),line(unknown,"content:demo"),duplicate] {
        println!("STRUCT {}",parse(&frame).unwrap_err());
    }
    let slots = |len| Value::Array((0..len).map(|i|json!({"id":format!("s{i}"),"language":"math","source":"x"})).collect());
    let limit=root(rich("limit","<p>x</p>",Some(slots(256))));
    let Node::RichText{inlines,..}=limit else {panic!("rich")};
    assert_eq!(inlines.len(),256);
    let max=rich("max","",Some(json!([{"id":"i".repeat(256),"language":"math","source":"x".repeat(32*1024)}])));
    assert!(matches!(parse(&line(max,"content:demo")),Ok(Incoming::View{..})));
    let dupe=json!([{"id":"s","language":"math","source":"1"},{"id":"s","language":"math","source":"2"}]);
    for bad in [slots(257),dupe,json!([{"id":"","language":"math","source":""}]),
                json!([{"id":"i","language":"","source":""}]),
                json!([{"id":"i","language":"math","source":"x".repeat(32*1024+1)}])]{
        let node=rich("bound","<p>x</p>",Some(bad));
        let panel=parse(&line(node.clone(),"panel")).unwrap_err().to_string();
        let Incoming::ContentError {error,view,session_dir,sequence,source_revision}=
            parse(&line(node,"content:demo")).unwrap() else {panic!("localized error")};
        assert_eq!(view,"content:demo");
        assert_eq!(session_dir.unwrap().to_str(),Some("/example/session"));
        assert_eq!((sequence,source_revision),(73,Some(97)));
        assert_eq!(error,panel);
        println!("VALIDATION {error}");
    }
    println!("PASS exact typed node envelope, required HTML/empty/Unicode and inline limits/localized validation");
}

fn plain() -> String {
    let sentence="Я иду &amp; снова увидел 🚀. <a href=\"https://example.com\">https://example.com</a>\r\n";
    format!("<div style=\"white-space: pre-wrap\">{}</div>",sentence.repeat(580))
}
fn markdown() -> String {
    let paragraph="<tr><td><strong>Данные</strong> &amp; <code>code</code></td><td>escaped &lt;text&gt;</td></tr>\n";
    format!("<table>{}</table><p>formula <span data-content=\"slot\">x &amp; y</span></p>\n",paragraph.repeat(520))
}
fn scope() {
    let app=App::default();
    const N:usize=24;
    let plain=plain();
    let markdown=markdown();
    let mut accepted=Vec::new();
    let mut native_memo_bytes=0;
    let mut total=0;
    for index in 0..N {
        let id=format!("body-{index}");
        let bytes=if index % 2 == 0 {&plain} else {&markdown};
        let node=root(rich(&id,bytes,None));
        let mut view=DeclarativeView {host:Some(3),layout_owner:Some(9),..Default::default()};
        adopt(node,&mut view,&app);
        let backing=view.root.as_ref().unwrap().clone();
        let memo=view.fields.rich_text.get(&id).unwrap();
        let state=memo.state.read(&app);
        assert_eq!(state.submitted, *bytes);
        assert!(!state.scrollable);
        assert_eq!(memo.html.as_str(),bytes);
        assert_eq!(memo.html.as_ptr()==html(&backing).as_ptr(),SHARED);
        assert_ne!(state.submitted.as_ptr(),html(&backing).as_ptr());
        if memo.html.as_ptr()!=html(&backing).as_ptr() {
            native_memo_bytes+=memo.html.len();
        }
        total+=bytes.len();
        drop(state);
        accepted.push(view);
    }
    assert_eq!(native_memo_bytes,if SHARED {0}else{total});
    assert_eq!(app.events.borrow().constructors.len(),N);
    assert!(app.events.borrow().text_updates.is_empty());
    eprintln!("WORK objects={N} plain_body_bytes={} gfm_body_bytes={} html_payload_bytes={total} duplicate_adapter_memo_bytes={native_memo_bytes}",plain.len(),markdown.len());
    assert_eq!(accepted.len(),N);
    println!("PASS retained long plain and GFM-style adapters hand the same bytes to the separately owned native state");
}

fn update_controls(){
    let a=markdown();
    let b=a.replacen("x &amp; y","u &amp; v",1);
    assert_eq!(a.len(),b.len());
    assert_ne!(a,b);
    let slot = |source:&str| Some(json!([{"id":"slot","language":"math","source":source}]));
    let mut view=DeclarativeView{host:Some(2),layout_owner:Some(8),source_revision:Some(7),accepted_source_revision:Some(7),
        ..Default::default()};
    let app=App::default();
    view.root=Some(Rc::new(root(rich("body",&a,slot("first")))));
    assert!(!view.ready(&app));
    assert!(view.layout_pending(&app));
    view.prepare_root(&mut Window,&mut Context::fixture(&app));
    assert!(!view.ready(&app));
    assert!(view.layout_pending(&app));
    let retained=view.root.as_ref().unwrap().clone();
    let loaded=&view.fields.rich_text["body"];
    assert!(!loaded.ready(&app));
    let same_entity=loaded.state.id;
    let saved_ptr=loaded.html.as_ptr();
    let retired_owner=weak_memo(loaded);
    assert_eq!(app.events.borrow().observers,1);
    loaded.state.value.borrow_mut().committed_revision=1;
    assert!(view.ready(&app));
    assert!(!view.layout_pending(&app));
    assert_eq!(loaded.element(),AnyElement{state:same_entity,selectable:true,inline_ids:vec!["slot".into()]});
    assert_eq!(saved_ptr==html(&retained).as_ptr(),SHARED);

    let equal_but_distinct=root(rich("body",&a,slot("changed nested source")));
    assert_ne!(html(&equal_but_distinct).as_ptr(),html(&retained).as_ptr());
    view.host=None;
    adopt(equal_but_distinct,&mut view,&app);
    let loaded=&view.fields.rich_text["body"];
    assert_eq!(loaded.html.as_ptr(),saved_ptr);
    assert_eq!(loaded.state.id,same_entity);
    assert!(view.ready(&app));
    let got=app.events.borrow();
    assert_eq!(got.entity_updates,0);
    assert_eq!(got.notifications,0);
    assert_eq!(got.text_updates.len(),0);
    assert_eq!(got.syncs[1],InlineCall{id:"body".into(),slots:vec![InlineContent{id:"slot".into(),language:"math".into(),source:"changed nested source".into()}],
        host:None,parent:Some(8),state:same_entity});
    drop(got);
    loaded.rehost(WeakEntity(PhantomData),&mut Window,&mut Context::fixture(&app));
    assert_eq!(app.events.borrow().rehost,1);
    assert_eq!(app.events.borrow().constructors.as_slice(),[a.as_str()]);
    drop(retained);
    if let Some(weak)=retired_owner.as_ref(){assert!(weak.upgrade().is_some());}
    view.source_revision=Some(8);
    assert!(view.layout_pending(&app));

    view.host=Some(42);
    adopt(root(rich("body",&b,slot("new"))),&mut view,&app);
    let next=&view.fields.rich_text["body"];
    assert_eq!(next.html.as_str(),b);
    assert_eq!(next.html.as_ptr()==html(view.root.as_ref().unwrap()).as_ptr(),SHARED);
    assert_eq!(next.state.id,same_entity);
    assert!(view.ready(&app)); // Old commit remains ready; source gate is separate.
    assert!(view.layout_pending(&app));
    let got=app.events.borrow();
    assert_eq!(got.entity_updates,1);
    assert_eq!(got.text_updates.as_slice(),[b.as_str()]);
    assert_eq!(got.syncs[2].host,Some(42));
    assert_eq!(got.syncs[2].slots[0].source,"new");
    drop(got);
    if let Some(weak)=retired_owner{assert!(weak.upgrade().is_none());}
    view.accepted_source_revision=Some(8);
    assert!(!view.layout_pending(&app));

    adopt(root(rich("body","",None)),&mut view,&app);
    assert!(view.fields.rich_text["body"].html.is_empty());
    assert_eq!(app.events.borrow().text_updates.as_slice(),[b.as_str(),""]);
    assert_eq!(app.events.borrow().syncs[3].slots.len(),0);
    view.error=Some("view error".into());
    assert!(!view.ready(&app));
    assert!(!view.layout_pending(&app));
    view.error=None;
    view.root=Some(Rc::new(root(json!({"type":"fill","children":[]}))));
    assert!(!view.ready(&app));
    println!("PASS exact memo retains byte-equal generation and native identity; inline-only values and host still reach sync; changed same-length and empty HTML set exact bytes");
    println!("PASS modeled commit/accepted readiness, selection call and rehost; old shared input releases after final holder");
}
pub fn run(){
    eprintln!("ARM {}",env!("R93_RICHTEXT_ARM"));
    wire_shape();
    scope();
    update_controls();
}
