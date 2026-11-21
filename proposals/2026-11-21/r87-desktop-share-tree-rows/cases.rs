use declarative::protocol::{parse,Incoming};

fn node(rows:Value,action:&str,indent:Option<f32>)->Value {
    let mut root=json!({"type":"tree","id":"files","action":action,"rows":rows});
    if let Some(indent)=indent { root["indent"]=json!(indent); }
    root
}
fn wire(root:Value,view:&str)->String {
    json!({"type":"view","view":view,"session_dir":"/example/session","sequence":7,
           "source_revision":31,"root":root}).to_string()
}
fn root(root:Value)->Node {
    let wire=wire(root,"panel");
    let received=std::thread::spawn(move||parse(&wire).unwrap()).join().unwrap();
    let Incoming::View {root,sequence,source_revision, ..}=received else{panic!("view")};
    assert_eq!((sequence,source_revision),(7,Some(31)));
    root
}
fn rows(root:&Node)->&[Row]{
    let Node::Tree {rows,..}=root else{panic!("tree")};
    rows.as_slice()
}
fn payload(order:bool)->Value {
    let mut value=serde_json::Map::new();
    if order {
        value.insert("a".to_owned(),json!(["opaque payload",{"path":"project/sample.rs"}]));
        value.insert("n".to_owned(),json!(-0.0));
    } else {
        value.insert("n".to_owned(),json!(0.0));
        value.insert("a".to_owned(),json!(["opaque payload",{"path":"project/sample.rs"}]));
    }
    Value::Object(value)
}
fn item(i:usize,selected:bool,menu_order:bool)->Value{
    json!({"id":format!("project/file-{i:04}.rs"),"label":format!("file-{i:04}.rs"),
           "detail":"workspace/project","hint":format!("full project path to file-{i:04}.rs"),
           "depth":1,"icon":"file-code","selected":selected, "checked":"mixed",
           "stats":{"added":4,"deleted":1},
           "menu":[
            {"label":"Files","header":true},
            {"label":"Open","action":"open_file","value":payload(menu_order),"icon":"file-code","checked":true,"separated":true},
            {"label":"Rename","action":"rename_file","value":{"path":"project/sample.rs"},"prompt":{"title":"Rename File"}},
            {"label":"Remove","action":"remove_file","value":{"path":"project/sample.rs"},"confirm":{"title":"Remove File"},"danger":true},
            {"label":"Disabled","action":"disabled_file","disabled":true}
           ]})
}
fn branch(open:bool)->Value{
    json!({"id":"project","label":"Project","kind":"header","expanded":open,"icon":"git-branch"})
}
fn other()->Value {json!({"id":"other","label":"Other","depth":0})}
fn menu_value(row:&Row)->String { row.menu[1].value.as_ref().unwrap().to_string() }
fn tree(view:&DeclarativeView)->std::cell::Ref<'_,Tree>{view.fields.trees["files"].0.borrow()}
fn tree_mut(view:&DeclarativeView)->std::cell::RefMut<'_,Tree>{view.fields.trees["files"].0.borrow_mut()}
fn row_key(view:&DeclarativeView,app:&App,key:&str){
    tree_mut(view).key(&KeyDownEvent{keystroke:KeyStroke{key:key.into()}},&mut Context::from(app));
}
fn validates(){
    let accepted=root(node(json!([]),"act",None));
    assert!(matches!(accepted,Node::Tree{indent:16.0,chevrons:true,guides:true,..}));
    assert!(rows(&accepted).is_empty());
    let dups=root(node(json!([{"id":"same","label":"one"},{"id":"same","label":"two"}]),"act",None));
    assert_eq!(rows(&dups).iter().map(|row|row.label.as_str()).collect::<Vec<_>>(),["one","two"]);
    let mut missing=node(json!([]),"act",None);
    missing.as_object_mut().unwrap().remove("rows");
    let mut unknown=node(json!([]),"act",None);
    unknown["misspelling"]=json!(true);
    let duplicate_rows=wire(node(json!([]),"act",None),"content:unit").replace(
        "\"rows\":[]", "\"rows\":[],\"rows\":[]");
    for line in [wire(missing,"content:unit"),wire(node(Value::Null,"act",None),"content:unit"),
        wire(node(json!({}),"act",None),"content:unit"),wire(node(json!([null]),"act",None),"content:unit"),
        wire(node(json!([{"id":"x","label":"x","checked":"wrong"}]),"act",None),"content:unit"),
        wire(node(json!([{"id":"x","label":"x","unknown":0}]),"act",None),"content:unit"),
        wire(unknown,"content:unit"),duplicate_rows] {
        let err=parse(&line).unwrap_err();
        println!("STRUCT {err}");
    }
    let invalids=[
        node(json!([]),"act",Some(65.0)),
        node(json!([{"id":"x","label":"x","icon":"bad-icon","menu":[{"label":"Also invalid"}]}]),"act",None),
        node(json!([{"id":"x","label":"x","menu":[{"label":"Also invalid"}]}]),"act",None),
        node(json!([{"id":"x","label":"x","menu":[{"label":"x","action":"x","selected":true,"checked":false}]}]),"act",None),
        node(json!([{"id":"x","label":"x","menu":[{"label":"x","action":"x","confirm":{"title":"x"},"prompt":{"title":"x"}}]}]),"act",None),
    ];
    for bad in invalids {
        let panel=parse(&wire(bad.clone(),"panel")).unwrap_err().to_string();
        let content=parse(&wire(bad,"content:unit")).unwrap();
        let Incoming::ContentError{view,session_dir,sequence,source_revision,error}=content else {panic!("retarget error")};
        assert_eq!(view,"content:unit");
        assert_eq!(session_dir.unwrap().to_str(),Some("/example/session"));
        assert_eq!((sequence,source_revision),(7,Some(31)));
        assert_eq!(panel,error);
        println!("VALIDATION {error}");
    }
    println!("PASS exact protocol shape, defaults, duplicate row IDs, actual row/menu validation and localized content errors");
}
fn large(){
    let large=|| {
        let many=std::iter::once(branch(true)).chain((0..1000).map(|i|item(i,i==23,true))).collect::<Vec<_>>();
        root(node(Value::Array(many),"files",None))
    };
    let mut view=DeclarativeView::default();
    let app=App::default();
    let mut cx=Context::from(&app);
    let initial=large();
    view.sync_tree(&initial,&mut cx);
    let t=tree(&view);
    let n=rows(&initial).len();
    assert_eq!(n,1001);
    assert_eq!(t.rows[24].id,"project/file-0023.rs");
    assert_eq!(t.cursor,24);
    assert_eq!(t.list.splices,[(0..0,1001)]);
    assert_eq!(rows(&initial),t.rows.as_slice());
    let aliases=t.rows.iter().zip(rows(&initial)).filter(|(live,root)|std::ptr::eq(*live,*root)).count();
    let labels=t.rows.iter().zip(rows(&initial)).filter(|(live,root)| live.label.as_ptr()==root.label.as_ptr()).count();
    let nested=t.rows.iter().zip(rows(&initial)).skip(1).filter(|(live,root)| {
        live.menu.as_ptr()==root.menu.as_ptr() &&
        live.menu[1].value.as_ref().unwrap()["a"][0].as_str().unwrap().as_ptr()==root.menu[1].value.as_ref().unwrap()["a"][0].as_str().unwrap().as_ptr()
    }).count();
    assert_eq!((aliases,labels,nested),if SHARED {(n,n,n-1)} else {(0,0,0)});
    let retained_distinct=n-aliases;
    eprintln!("WORK initial_rows={} distinct_native_row_slots={} duplicate_row_slots_bytes={} shared_nested_menu_payloads={}",
        n,retained_distinct,retained_distinct*std::mem::size_of::<Row>(),nested);
    let first=t.rows.as_ptr();
    drop(t);
    let equal=large();
    assert_ne!(rows(&equal).as_ptr(),first);
    assert_eq!(rows(&equal),rows(&initial));
    let (calls,bytes)=counted(||view.sync_tree(&equal,&mut cx));
    if SHARED { assert_eq!((calls,bytes),(0,0)); }
    else { assert!(calls > 1000 && bytes> 1001*std::mem::size_of::<Row>()); }
    assert_eq!(tree(&view).rows.as_ptr(),first);
    assert_eq!(tree(&view).list.splices,[(0..0,1001)]);
    assert_eq!(app.0.borrow().notifications,0);
    eprintln!("WORK equal_refresh_rows={} handoff_allocator_requests={} requested_bytes={} independent_current_root=true",
        n,calls,bytes);
    println!("PASS large mount: exact 1001-row order, selection, value-equivalent reuse, no equal-update notify or splice");
}
fn lifecycle() {
    let original=root(node(json!([branch(true),item(1,true,true),item(2,false,true),other()]),"old_route",None));
    let refreshed=root(node(json!([branch(true),item(1,true,false),item(2,false,false),other()]),"new_route",None));
    let mut view=DeclarativeView{embedded:true,..DeclarativeView::default()};
    let app=App::default();
    let mut cx=Context::from(&app);
    assert_eq!(rows(&original),rows(&refreshed));
    assert_ne!(menu_value(&rows(&original)[1]),menu_value(&rows(&refreshed)[1]));
    view.sync_tree(&original,&mut cx);
    let old_backing=owner(&tree(&view));
    let old_ptr=tree(&view).rows.as_ptr();
    let installed_menu=tree(&view).observed_menu(1);
    assert_eq!(tree(&view).active_guide(),Some((1..3,0)));
    assert!(tree(&view).natural);
    view.sync_tree(&refreshed,&mut cx);
    assert_eq!(tree(&view).rows.as_ptr(),old_ptr);
    assert_eq!(menu_value(&tree(&view).rows[1]),menu_value(&rows(&original)[1]));
    assert_eq!(app.0.borrow().notifications,0);
    row_key(&view,&app,"enter");
    assert_eq!(app.0.borrow().actions, [("new_route".into(),json!({"id":"project/file-0001.rs","event":"open"}))]);
    let old_value=menu_value(&rows(&original)[1]);
    drop(refreshed);
    // Layout changes still pass the old gate even when rows compare equal.
    let relaid=root(node(json!([branch(true),item(1,true,false),item(2,false,false),other()]),"new_route",Some(22.0)));
    view.sync_tree(&relaid,&mut cx);
    assert_eq!(tree(&view).layout.indent,22.0);
    assert_eq!(tree(&view).list.splices,[(0..0,4),(4..4,0)]);
    assert_eq!(tree(&view).rows.as_ptr()==rows(&relaid).as_ptr(),SHARED);
    assert_eq!(menu_value(&tree(&view).rows[1]),menu_value(&rows(&relaid)[1]));
    drop(original);
    if let Some(weak)=old_backing {assert!(weak.upgrade().is_none());}
    let closing_backing=owner(&tree(&view));
    let closing_value=menu_value(&rows(&relaid)[1]);
    let closed=root(node(json!([branch(false),other()]),"closed_route",Some(22.0)));
    app.0.borrow_mut().moving=true;
    view.sync_tree(&closed,&mut cx);
    drop(relaid);
    if let Some(weak)=closing_backing {assert!(weak.upgrade().is_none());}
    let mut t=tree_mut(&view);
    assert_eq!(t.rows.as_ptr()==rows(&closed).as_ptr(),SHARED);
    assert_eq!(t.list.splices,[(0..0,4),(4..4,0),(1..3,0)]);
    assert_eq!(t.list.reveals,[1]);
    assert_eq!(t.cursor,1);
    assert_eq!(t.folds.len(),1);
    assert_eq!((t.folds[0].id.as_str(),t.folds[0].open),("project",false));
    assert_eq!(t.folds[0].gone.iter().map(|r|r.id.as_str()).collect::<Vec<_>>(),["project/file-0001.rs","project/file-0002.rs"]);
    assert_eq!(menu_value(&t.folds[0].gone[0]),closing_value);
    let span=t.spans(&app);
    assert_eq!((span[0].branch,span[0].children.clone(),span[0].fold),(0,1..1,0));
    app.0.borrow_mut().moving=false;
    assert!(t.spans(&app).is_empty());
    assert!(t.folds.is_empty());
    assert_eq!(t.list.remeasures,[0..1]);
    drop(t);
    assert_eq!(app.0.borrow().motions,[("tree-77-project".into(),false)]);
    assert_eq!(app.0.borrow().notifications,2);
    let menu=installed_menu();
    let labels=menu.0.iter().map(|r|r.as_ref().map(|r|r.name.as_str())).collect::<Vec<_>>();
    assert_eq!(labels,[Some("Files"),None,Some("Open"),Some("Rename"),Some("Remove"),Some("Disabled")]);
    assert!(menu.0[0].as_ref().unwrap().click.is_none());
    assert!(menu.0[5].as_ref().unwrap().disabled);
    assert_eq!(menu.0[2].as_ref().unwrap().icon.as_deref(),Some("file-code"));
    assert_eq!(menu.0[2].as_ref().unwrap().checked,Some(true));
    for index in 2..=4 {
        menu.0[index].as_ref().unwrap().click.as_ref().unwrap()(&mut menu::Window,&mut app.clone());
    }
    let events=&app.0.borrow().menus;
    assert_eq!(events.iter().map(|(a,_,k)|(a.as_str(),k.as_str())).collect::<Vec<_>>(),
               [("open_file","none"),("rename_file","prompt:Rename File"),("remove_file","confirm:Remove File")]);
    assert_eq!(events[0].1.as_ref().unwrap().to_string(),old_value);
    assert_eq!(events[1].1.as_ref().unwrap()["path"],"project/sample.rs");
    println!("PASS row action rebind through equal gate; old ordered menu payload, prompt and confirmation survive view refresh");
    println!("PASS exact layout/cursor/splice/reveal and detached closing snapshot; old row owner does not pin a Fold");
}
fn navigate(){
    let root=root(node(json!([branch(false),
        {"id":"section","label":"Section B","kind":"header","expanded":false}]),"route",None));
    let mut view=DeclarativeView::default();
    let app=App::default();
    view.sync_tree(&root,&mut Context::from(&app));
    for key in ["down","enter","up","space"] {row_key(&view,&app,key);}
    assert_eq!(app.0.borrow().actions,[("route".into(),json!({"id":"section","event":"expand"})),
                                     ("route".into(),json!({"id":"project","event":"expand"}))]);
    assert_eq!(tree(&view).cursor,0);
    println!("PASS keyboard navigation keeps header-only sections reachable");
}
pub fn run() {
    eprintln!("ARM {}",env!("R87_TREE_PROBE_ARM"));
    validates();large();lifecycle();navigate();
}
