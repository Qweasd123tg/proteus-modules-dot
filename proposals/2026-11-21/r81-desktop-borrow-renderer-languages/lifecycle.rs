
use crate::{carrier::*, declarative::manifest, ledger, preferences};
use serde_json::{Value,json};
use std::{collections::HashSet,fs,path::PathBuf,rc::Rc,sync::Arc};
use super::replies::{Part,Replies};
use crate::ui::extensions::{content, declarative::{current_manifest, rescan_now, inline_content}};
const LANGS: [(&str,&str);5] = [
    ("json-render","json-render"),("svg","json-render"),("md","markdown-render"),
    ("markdown","markdown-render"),("mermaid","mermaid-render"),
];
fn view_name(s: &impl AsRef<str>) -> &str { s.as_ref() }
fn latest(cx:&App)->(usize,usize,usize,usize,usize) {
    let e=cx.events.borrow();
    (e.created,e.set_source,e.set_content,e.notified,e.wire.len())
}
fn part(replies:&mut Replies, key:u64, source:&Arc<str>, cx:&mut Context<Chat>)->Part {
    let media=if key % 2 == 0 {"text/markdown"} else {"text/plain"};
    replies.part(key,media,source,WeakEntity::default(),ChatKey,key%2==0,&mut Window,cx)
}
fn entity(part:Part)->Entity<content::ContentView> {
    let Part::Content(view)=part else { panic!("renderer expected"); };
    view
}
fn summarize(cx:&App)->Vec<(String,&'static str)> {
    content::languages(cx).iter().map(|(name,id)|(view_name(name).to_owned(),*id)).collect()
}
fn record(label:&str,cx:&App) {
    let (created,offered,applied,notified,wire)=latest(cx);
    println!("PASS {label} created={created} offered={offered} applied={applied} notified={notified} wire={wire}");
}
fn lookup(needle:&str,expect:Option<&str>,candidate:bool,prefix:usize,cx:&App) {
    ledger::reset();
    assert_eq!(content::language_renderer(needle,cx),expect);
    assert_eq!(ledger::counts(),if candidate {(0,prefix)} else {(5,5)});
    println!("PASS lookup {needle:?} {expect:?}");
    eprintln!("WORK lookup {needle:?} clones={} yielded={}",ledger::counts().0,ledger::counts().1);
}
fn ext_path(id:&str)->PathBuf { manifest::root().unwrap().join(id) }
fn make_package(id:&str,langs:&[&str],formats:&[&str]) {
    let dir=ext_path(id);
    fs::create_dir_all(&dir).unwrap();
    fs::write(dir.join("extension.json"),json!({
        "id":id,"title":id,"protocol":4,"command":["fixture-no-exec"],
        "surfaces":{"content":{"languages":langs,"formats":formats}}
    }).to_string()).unwrap();
}
fn move_away(id:&str) {
    fs::rename(ext_path(id),ext_path(&format!(".hidden-{id}"))).unwrap();
}
fn revision(view:&Entity<content::ContentView>)->Option<u64> { view.0.borrow().content.source_revision }
fn check_installed_pointers(replies:&Replies,key:u64,candidate:bool) {
    for (name,id) in replies.remembered(key) {
        let orig=current_manifest(id).unwrap()
            .manifest.surfaces.content.as_ref().unwrap().languages.iter().find(|actual| actual.as_str()==name).unwrap();
        assert_eq!(orig.as_ptr()==name.as_ptr(),candidate);
    }
}

pub(crate) fn run(candidate:bool) {
    let bundle=manifest::bundled_root();
    let xdg=preferences::config_dir().expect("isolated scratch config");
    assert_eq!(bundle,std::env::current_dir().unwrap().join("bundled"));
    assert_eq!(xdg,std::env::current_dir().unwrap().join("config/fixture-r81"));
    fs::create_dir_all(manifest::root().unwrap()).unwrap();
    let (actual,errors)=manifest::discover_sources(&bundle,manifest::root().as_deref());
    assert!(errors.is_empty(),"{errors:?}");
    assert_eq!(actual.iter().map(|entry| entry.manifest.id.as_str()).collect::<Vec<_>>(), ["json-render","markdown-render","mermaid-render"]);
    for entry in actual { assert_eq!(entry.manifest.id,entry.dir.file_name().unwrap().to_str().unwrap()); }
    let mut cx=Context::<Chat>::default();
    assert_eq!(content::format("text/plain",&cx),Some("markdown-render"));
    assert_eq!(content::format("text/markdown",&cx),Some("markdown-render"));
    assert_eq!(content::format("md",&cx),None);
    assert_eq!(summarize(&cx),LANGS.map(|(n,id)|(n.to_owned(),id)));
    println!("PASS exact bundled filesystem discovery and default contributor/media order");
    
    let mut replies=Replies::default();
    let rows:Vec<_>=(0..8).map(|i| Arc::<str>::from(format!("Row {i} — naïve → русский 🦀"))).collect();
    let views:Vec<_>=rows.iter().enumerate().map(|(i,row)|entity(part(&mut replies,i as u64,row,&mut cx))).collect();
    assert_eq!(latest(&cx),(8,0,0,0,8));
    assert!(views.iter().all(|view|revision(view)==Some(0)));
    assert!(views.iter().enumerate().all(|(i,v)|
        v.0.borrow().host.ext=="markdown-render" && v.0.borrow().host.readonly==(i%2==0)));
    for i in 0..8 { check_installed_pointers(&replies,i,candidate); }
    record("eight-cold-reply-contexts",&cx);
    for rounds in [1,5] {
        ledger::reset();
        for _ in 0..rounds {
            for (i,row) in rows.iter().enumerate() {
                let now=entity(part(&mut replies,i as u64,row,&mut cx));
                assert!(Rc::ptr_eq(&now.0,&views[i].0));
            }
        }
        assert_eq!(ledger::counts(),(if candidate {0}else{rounds*40},rounds*40));
        assert_eq!(latest(&cx),(8,0,0,0,8));
        record(&format!("same-rows-{}-warm-renders",rounds*8),&cx);
        eprintln!("WORK warm renders={} clones={} yielded={}",rounds*8,ledger::counts().0,ledger::counts().1);
    }

    lookup("md",Some("markdown-render"),candidate,3,&cx);
    lookup("mermaid",Some("mermaid-render"),candidate,5,&cx);
    lookup("missing",None,candidate,5,&cx);
    lookup("SVG",None,candidate,5,&cx);
    lookup("λ",None,candidate,5,&cx);
    let queries=["svg","md","mermaid","SVG","λ"].map(str::to_owned);
    assert_eq!(inline_content::resolve(&queries,&cx),[Some("json-render"),Some("markdown-render"),Some("mermaid-render"),None,None]);
    println!("PASS exact inline selection agrees with direct lookup and missing fallback");

    for id in ["unicode-invalid","repeated-invalid"] {
        let names=if id=="unicode-invalid" {["svg","λ"]} else {["svg","svg"]};
        make_package(id,&names,&[]);
        let (_,errs)=manifest::discover_sources(&bundle,manifest::root().as_deref());
        assert!(errs.iter().any(|p|p.dir.ends_with(id) && p.error.contains("unique lowercase fence identifiers")));
        move_away(id);
    }
    println!("PASS exact manifest rejects Unicode and same-package duplicate identifiers");

    cx.prefs().order = ["json-render","markdown-render","mermaid-render"].map(str::to_owned).to_vec();
    let old_json=current_manifest("json-render").unwrap();
    let old_snapshot=content::languages(&cx);
    assert_eq!(old_json.dir.parent(),Some(bundle.as_path()));
    // Keep exact identical names in a physically distinct user override generation.
    let user_dir=ext_path("json-render");
    fs::create_dir_all(user_dir.join("skills/visualize")).unwrap();
    fs::copy(old_json.dir.join("extension.json"),user_dir.join("extension.json")).unwrap();
    fs::copy(old_json.dir.join("skills/visualize/SKILL.md"),user_dir.join("skills/visualize/SKILL.md")).unwrap();
    rescan_now();
    let new_json=current_manifest("json-render").unwrap();
    let new_snapshot=content::languages(&cx);
    assert!(!std::ptr::eq(old_json,new_json));
    assert_eq!(old_json.manifest,new_json.manifest);
    assert_eq!(old_snapshot,new_snapshot);
    assert_eq!(new_json.dir,user_dir);
    assert!(Rc::ptr_eq(&entity(part(&mut replies,0,&rows[0],&mut cx)).0,&views[0].0));
    assert_eq!(latest(&cx),(8,0,0,0,8));
    record("equal-generation-replacement-no-op",&cx);

    let old_generation_ptr=old_json.manifest.surfaces.content.as_ref().unwrap().languages[0].as_ptr();
    let new_generation_ptr=new_json.manifest.surfaces.content.as_ref().unwrap().languages[0].as_ptr();
    assert_ne!(old_generation_ptr,new_generation_ptr);
    let recalled=replies.remembered(0);
    assert_eq!(recalled[0].0.as_ptr()==old_generation_ptr,candidate);
    assert_ne!(recalled[0].0.as_ptr(),new_generation_ptr);
    drop(recalled);

    // In-place manifest change updates the real catalog through its validated rescan.
    let mut add:Value=serde_json::from_slice(&fs::read(user_dir.join("extension.json")).unwrap()).unwrap();
    add["surfaces"]["content"]["languages"].as_array_mut().unwrap().push(json!("new-renderer"));
    fs::write(user_dir.join("extension.json"),serde_json::to_vec(&add).unwrap()).unwrap();
    rescan_now();
    assert_eq!(view_name(&old_snapshot[0].0),"json-render");
    assert_eq!(old_snapshot.len(),5);
    assert_eq!(content::language_renderer("new-renderer",&cx),Some("json-render"));
    let changed=entity(part(&mut replies,0,&rows[0],&mut cx));
    assert!(Rc::ptr_eq(&changed.0,&views[0].0));
    assert_eq!(revision(&changed),Some(1));
    assert_eq!(latest(&cx),(8,1,1,1,9));
    record("fresh-manifest-add-registration",&cx);

    cx.prefs().order = ["json-render","markdown-render","mermaid-render","alt-a","alt-b"].map(str::to_owned).to_vec();
    make_package("alt-a",&["svg"],&[]);
    rescan_now();
    assert_eq!(content::language_renderer("svg",&cx),Some("json-render"));
    let updated=entity(part(&mut replies,0,&rows[0],&mut cx));
    assert_eq!(revision(&updated),Some(2));
    assert_eq!(latest(&cx),(8,2,2,2,10));
    let original_wire=updated.0.borrow().content.context.clone();
    assert_eq!(original_wire["contributors"]["svg"],"json-render");
    assert_eq!(original_wire["languages"].as_array().unwrap().iter().filter(|v| **v=="svg").count(),2);
    assert!(replies.remembered(0).contains(&("svg","alt-a")));

    // A shadowed claimant changes the pair in Reply but not the payload or revision.
    move_away("alt-a");
    make_package("alt-b",&["svg"],&[]);
    rescan_now();
    let final_alias=entity(part(&mut replies,0,&rows[0],&mut cx));
    assert!(Rc::ptr_eq(&final_alias.0,&views[0].0));
    assert_eq!(final_alias.0.borrow().content.context,original_wire);
    assert_eq!(revision(&final_alias),Some(2));
    assert_eq!(latest(&cx),(8,3,2,2,10));
    assert!(replies.remembered(0).contains(&("svg","alt-b")));
    record("shadowed-claimant-value-change-no-wire-update",&cx);

    cx.prefs().order=["alt-b","json-render","json-render","markdown-render"].map(str::to_owned).to_vec();
    assert_eq!(content::language_renderer("svg",&cx),Some("alt-b"));
    let mut ctx=json!({"opaque":{"ordered":["first","next"],"text":"λ 🦀"},"contributors":{"ignore":0},"languages":[false],"tail":17});
    content::context(&mut ctx,&cx);
    assert_eq!(ctx.as_object().unwrap().keys().map(String::as_str).collect::<Vec<_>>(),["opaque","contributors","languages","tail"]);
    assert_eq!(ctx["languages"].as_array().unwrap().iter().filter(|v| **v=="svg").count(),3);
    assert_eq!(ctx["contributors"]["svg"],"alt-b");
    assert_eq!(ctx["opaque"]["text"],"λ 🦀");
    assert_eq!(inline_content::resolve(&["svg".into()],&cx),[Some("alt-b")]);
    println!("WIRE opaque {}",serde_json::to_string(&ctx).unwrap());
    assert_eq!(revision(&entity(part(&mut replies,0,&rows[0],&mut cx))),Some(3));
    record("reorder-first-claim-and-repeated-saved-ids",&cx);

    cx.prefs().set_enabled("alt-b",false);
    assert_eq!(content::language_renderer("svg",&cx),Some("json-render"));
    for mut plain in [Value::Null,json!(["x",5]),json!("old")] {
        content::context(&mut plain,&cx);
        assert_eq!(plain.as_object().unwrap().keys().map(String::as_str).collect::<Vec<_>>(),["languages","contributors"]);
        println!("WIRE nonobject {}",serde_json::to_string(&plain).unwrap());
    }
    assert_eq!(revision(&entity(part(&mut replies,0,&rows[0],&mut cx))),Some(4));
    record("disabled-duplicate-falls-back",&cx);

    cx.prefs().set_enabled("markdown-render",false);
    assert_eq!(content::language_renderer("md",&cx),None);
    assert_eq!(content::format("text/plain",&cx),None);
    let Part::Plain(fallback)=part(&mut replies,0,&rows[0],&mut cx) else {panic!("plain fallback")};
    assert!(Arc::ptr_eq(&fallback,&rows[0]));
    record("disabled-full-body-plain-fallback",&cx);
    cx.prefs().set_enabled("markdown-render",true);
    let replaced=entity(part(&mut replies,0,&rows[0],&mut cx));
    assert!(!Rc::ptr_eq(&replaced.0,&views[0].0));
    assert_eq!(revision(&replaced),Some(0));
    record("reenabled-body-recreated",&cx);

    let weak=Rc::downgrade(&replaced.0);
    drop(replaced);
    replies.retain(&HashSet::new());
    assert!(weak.upgrade().is_none());
    record("retained-row-removal-releases-modeled-view",&cx);
    for wire in &cx.events.borrow().wire { println!("WIRE view {wire}"); }
}
