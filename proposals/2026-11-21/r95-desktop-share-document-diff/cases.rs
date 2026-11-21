use declarative::protocol::{parse,Incoming};

fn node(patch:&str,files:Option<Value>,height:Option<Value>)->Value {
    let mut root=json!({"type":"diff","id":"changes","patch":patch});
    if let Some(files)=files{root["files"]=files;}
    if let Some(h)=height{root["height"]=h;}
    root
}
fn frame(root:Value,view:&str)->String {
    json!({"type":"view","view":view,"session_dir":"/example/session","sequence":11,"source_revision":18,"root":root}).to_string()
}
fn root(root:Value)->Node {
    let wire=frame(root,"panel");
    let Incoming::View {root,sequence:11,source_revision:Some(18),..}=
        std::thread::spawn(move||parse(&wire).unwrap()).join().unwrap() else {panic!("view envelope")};
    root
}
fn source(node:&Node)->&str {
    let Node::Diff{patch,..}=node else{panic!("diff")};
    patch.as_str()
}
fn prepare(view:&mut DeclarativeView,node:Node,app:&App) {
    let root=Rc::new(node);
    view.sync_document(&root,&mut Context::from(app));
    view.root=Some(root);
}
fn entity(view:&DeclarativeView)->&Entity<DiffView>{&view.fields.diffs["changes"]}
fn item(view:&DeclarativeView)->Ref<'_,DiffView>{entity(view).0.borrow()}
fn own(view:&DeclarativeView)->&str{source(view.root.as_ref().unwrap())}
fn patch(view:&DiffView)->&str{view.patch.as_str()}

fn wire_shape(){
    let empty=root(node("",None,None));
    assert!(matches!(&empty,Node::Diff{height:None,files,..} if files.is_empty()));
    assert!(source(&empty).is_empty());
    let text="\r\n*** Add File: data.txt\r\n+ёлка 🚀\r\n";
    assert_eq!(source(&root(node(text,None,None))),text);
    let mut missing=node("",None,None);missing.as_object_mut().unwrap().remove("patch");
    let null=||{let mut n=node("",None,None);n["patch"]=Value::Null;n};
    let array=||{let mut n=node("",None,None);n["patch"]=json!(["x"]);n};
    let field=||{let mut n=node("",None,None);n["bad"]=json!(true);n};
    let duplicate=frame(node("",None,None),"content:shape")
        .replace("\"patch\":\"\"","\"patch\":\"\",\"patch\":\"b\"");
    let malformed_metadata=node("",Some(json!([{"path":"x","wrong":0}])),None);
    for wire in [frame(missing,"content:shape"),frame(null(),"content:shape"),frame(array(),"content:shape"),
        frame(field(),"content:shape"),duplicate,frame(malformed_metadata,"content:shape")] {
        println!("STRUCT {}",parse(&wire).unwrap_err());
    }
    for n in [node("",None,Some(json!(0))),node("",None,Some(json!(-4)))]{
        let err=parse(&frame(n.clone(),"panel")).unwrap_err();
        let Incoming::ContentError{error,sequence,source_revision,..}=
            parse(&frame(n,"content:shape")).unwrap() else {panic!("localized height check")};
        assert_eq!(error,err.to_string());assert_eq!((sequence,source_revision),(11,Some(18)));
        println!("VALIDATION {error}");
    }
    println!("PASS exact DTO and parser guards: required, empty, UTF-8, malformed and duplicate patch, metadata and height");
}
fn raw_patch(name:&str,ending:bool)->String{
    let mut patch=format!("diff --git a/{name} b/{name}\r\n--- a/{name}\r\n+++ b/{name}\r\n@@ -0,0 +1,1200 @@\r\n");
    for i in 0..1200{
        use std::fmt::Write;
        write!(&mut patch,"+row {i:04} | пример: reviewed change on a normal document line").unwrap();
        if i!=1199 || ending {patch.push_str("\r\n");}
    }
    patch
}
fn document_lifecycle(){
    // Anchors deliberately include CRLF, leading bytes and omitted apply_patch
    // wrapper markers between real blocks; only per-file reconstructions omit them.
    let f1=raw_patch("src/old.rs",true);
    let f2=raw_patch("src/new.rs",false);
    let a=format!("\r\n*** Begin Patch\r\n{f1}*** End of File\r\n{f2}");
    let b=format!("\r\n*** Begin Patch\r\n{}*** End of File\r\n{}",raw_patch("src/new.rs",true),raw_patch("src/old.rs",false));
    let missing=json!([{"path":"bin/icon.png","status":"modified","message":"Binary"}]);
    let app=App::default();
    let mut view=DeclarativeView::default();
    let mut cx=Context::from(&app);
    prepare(&mut view,root(node(&a,Some(missing.clone()),None)),&app);
    let retained=view.root.as_ref().unwrap().clone();
    let p=item(&view).patch.as_str().as_ptr();
    assert_eq!(patch(&item(&view)),a);
    assert_eq!(p==own(&view).as_ptr(),SHARED);
    assert_eq!(is_owned(&item(&view)),!SHARED);
    assert_eq!(item(&view).files.len(),3);
    assert_eq!(item(&view).files[0].path,"src/old.rs");
    assert_eq!(item(&view).files[1].patch.as_str(),f2);
    assert!(item(&view).files[2].patch.is_empty());
    let retired_owner=weak(&item(&view));
    let owner_count=if SHARED{0}else{a.len()};
    let all_button=item(&view).copy_all(&mut cx);
    assert_eq!(all_button.hint,"Копировать весь diff");
    let old_file=Rc::clone(&item(&view).files[0]);
    let file_weak=Rc::downgrade(&old_file);
    let file_button=copy_file(old_file,&mut cx);
    assert_eq!(file_button.hint,"Копировать diff файла");
    assert!(!all_button.disabled && !file_button.disabled);
    assert!(copy_file(Rc::clone(&item(&view).files[2]),&mut cx).disabled);
    let first_syntax=Rc::clone(&item(&view).syntax[0]);
    let old_focus=item(&view).file_focus.clone();
    {
        let mut diff=entity(&view).0.borrow_mut();
        diff.horizontal[0][1]=ScrollHandle(55);
        diff.folded.insert("src/old.rs".into());
        diff.folded.insert("bin/icon.png".into());
        diff.measured=Some((Font,12.0,vec![13.0]));
        diff.list.as_ref().unwrap().0.borrow_mut().anchor=ListOffset{item_ix:0,offset_in_item:17.0};
    }
    prepare(&mut view,root(node(&a,Some(missing),None)),&app);
    assert_ne!(source(&retained).as_ptr(),own(&view).as_ptr());
    assert_eq!(patch(&item(&view)).as_ptr(),p);
    assert_eq!(app.e.borrow().notify,0);
    assert!(item(&view).measured.is_some());
    assert!(item(&view).list.as_ref().unwrap().0.borrow().remeasures.is_empty());
    assert!(Rc::ptr_eq(&first_syntax,&item(&view).syntax[0]));
    all_button.press(entity(&view),&mut cx);
    assert_eq!(app.e.borrow().clipboard[0],a);

    // Same raw bytes plus changed metadata must still go through the old update gate.
    let new_missing=json!([{"path":"bin/icon.png","status":"deleted","message":"unavailable"}]);
    prepare(&mut view,root(node(&a,Some(new_missing.clone()),None)),&app);
    assert_eq!(patch(&item(&view)).as_ptr()==own(&view).as_ptr(),SHARED);
    assert_eq!(app.e.borrow().notify,1);
    assert!(item(&view).measured.is_none());
    assert_eq!(item(&view).list.as_ref().unwrap().0.borrow().remeasures,[0..3,0..3]);
    assert_eq!(item(&view).files[2].status,"deleted");
    assert_eq!(item(&view).files[2].lines[0].text,"unavailable");
    assert!(Rc::ptr_eq(&first_syntax,&item(&view).syntax[0]));
    assert_eq!(item(&view).file_focus,old_focus);
    drop(retained);
    if let Some(weak)=retired_owner{assert!(weak.upgrade().is_none());}

    prepare(&mut view,root(node(&b,None,None)),&app);
    assert_eq!(own(&view),b);
    assert_eq!(patch(&item(&view)),b);
    assert_eq!(patch(&item(&view)).as_ptr()==own(&view).as_ptr(),SHARED);
    let after_count=if SHARED{0}else{b.len()};
    assert_eq!(app.e.borrow().notify,2);
    assert_eq!(item(&view).file_focus,[old_focus[1].clone(),old_focus[0].clone()]);
    assert_eq!(item(&view).horizontal[1][1],ScrollHandle(55));
    assert_eq!(item(&view).folded,HashSet::from(["src/old.rs".to_owned()]));
    let list=item(&view);
    let data=list.list.as_ref().unwrap().0.borrow();
    assert_eq!(data.splices,[(0..3,2)]);
    assert_eq!(data.scroll,[ListOffset{item_ix:1,offset_in_item:17.0}]);
    drop(data);drop(list);
    assert!(file_weak.upgrade().is_none());
    all_button.press(entity(&view),&mut cx);
    file_button.press(&mut cx);
    assert_eq!(app.e.borrow().clipboard,[a.clone(),b.clone(),f1.clone()]);
    assert_eq!(app.e.borrow().stopped,1);
    assert_eq!(app.e.borrow().resize,0);
    eprintln!("WORK mount_raw_bytes={} mount_duplicate_native_bytes={owner_count} changed_raw_bytes={} changed_duplicate_native_bytes={after_count}",a.len(),b.len());
    println!("PASS full Git raw backing, equal guard, metadata-only reparse, focus/syntax/hscroll/fold and viewport anchor");
    println!("PASS existing live Copy All callback receives new whole bytes, historical Copy File retains only old parsed block; CRLF, wrappers and missing final LF remain exact");
    prepare(&mut view,root(node("",Some(new_missing),None)),&app);
    let disabled=item(&view).copy_all(&mut cx);
    assert!(disabled.disabled);
    disabled.press(entity(&view),&mut cx);
    assert_eq!(app.e.borrow().clipboard.len(),3);
}
fn embedded_control(){
    let app=App::default();
    let mut cx=Context::from(&app);
    let mark="*** Add File: fixture.txt\n+first\n";
    let owned=mark.to_owned();
    let pointer=owned.as_ptr();
    let mut inline=DiffView::embedded(owned,vec![],&mut cx);
    assert!(is_owned(&inline));
    assert_eq!(patch(&inline).as_ptr(),pointer);
    assert!(inline.list.is_none());
    inline.set_patch(mark,&[],&mut cx);
    assert_eq!(patch(&inline).as_ptr(),pointer);
    assert_eq!((app.e.borrow().notify,app.e.borrow().resize),(0,0));
    let next="*** Add File: fixture.txt\n+second";
    inline.set_patch(next,&[],&mut cx);
    assert!(is_owned(&inline));
    assert_eq!(patch(&inline),next);
    assert_eq!((app.e.borrow().notify,app.e.borrow().resize),(1,1));
    println!("PASS embedded chat retains String backing and resize behavior, without a shared-header allocation");
}
pub fn run(){
    eprintln!("ARM {}",env!("R95_DIFF_ARM"));
    wire_shape();document_lifecycle();embedded_control();
}
