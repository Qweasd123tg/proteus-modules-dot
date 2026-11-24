use super::{TextSystem,OnceLock};
use crate::meter::{measure,Count};
use fontdb::{Database, FaceInfo, ID, Language, Source, Stretch, Style, Weight};
use std::{hash::{DefaultHasher,Hash,Hasher},sync::Arc};

fn register(db:&mut Database,i:usize,name:Option<&str>,localized:bool) {
    let mut families=name.into_iter().map(|s|(s.to_owned(),Language::English_UnitedStates)).collect::<Vec<_>>();
    if localized && !families.is_empty(){families.push((format!("unused alias {i}"),Language::English_UnitedStates));}
    db.push_face_info(FaceInfo {
      id: ID::dummy(), source:Source::Binary(Arc::new(Vec::<u8>::new())), index:i as u32,
      families, post_script_name:format!("Fixture-{i}"),style:if i%2==0{Style::Normal}else{Style::Italic},
      weight:if i%3==0 {Weight::BOLD}else{Weight::NORMAL}, stretch:Stretch::Normal, monospaced:i%2==0
    });
}
fn digest(xs:&[String])->u64 {let mut h=DefaultHasher::new();xs.hash(&mut h);h.finish()}
fn print(label:&str,faces:usize,raw:(&[String],usize),count:Count) {
    let (names,cap)=raw;
    println!("FONT {label} {faces} {} {cap} {} {} {} {} {}",names.len(),digest(names),count.live,count.requests,count.bytes,count.peak);
}
fn pair(db:Database,label:&str){
    let faces=db.faces().count();
    let mut reference:Vec<_>=db.faces().filter_map(|f|f.families.first().map(|name|name.0.clone())).collect();
    reference.sort_unstable();reference.dedup();
    let filtered:Vec<_>=reference.iter().filter(|name|!name.trim().is_empty()).map(String::as_str).collect();
    let text=TextSystem::new(db);
    let cache=OnceLock::new();
    let (desktop,c)=measure(||{
        assert_eq!(text.component_names(&cache),reference.is_empty());
        text.desktop_names()
    });
    let old=cache.get().unwrap();
    assert_eq!(old,&reference);
    assert_eq!(desktop.iter().map(|x| x.as_str()).collect::<Vec<_>>(),filtered);
    print(label,faces,(old,old.capacity()),c);
}
#[test]
fn real_typed_face_inventory_and_picker_are_stable() {
    for (label,count,distinct) in [("empty",0,1),("dense",2048,64),("unique",1024,1024),("mixed",571,253)] {
       let mut db=Database::new();
       for i in 0..count{
           let n=(i*17)%distinct;
           // Include locale/case variations; matching stays byte exact.
           let name=format!("Fixture {} family {n:04}",["Álphabet A","1","中文","Åä"][n%4]);
           register(&mut db,i,Some(&name),true);
       }
       pair(db,label);
    }
    let mut db=Database::new();
    for (i,n) in [Some("お茶"),None,Some(""),Some("  "),Some("Α"),Some("a"),Some("A"),Some("A"),Some("a"),Some(".SystemUIFont")].into_iter().enumerate(){
       register(&mut db,i,n,true);
    }
    pair(db,"edge");
}
#[test]
fn next_real_database_query_observes_added_and_removed_families() {
    let text=TextSystem::new(Database::new());
    assert!(text.all_font_names().is_empty());
    let id={
        let mut state=text.platform_text_system.0.0.write().unwrap();
        let db=&mut state.font_system.0;
        register(db,1,Some("First"),true);
        db.faces().next().unwrap().id
    };
    assert_eq!(text.all_font_names(),["First"]);
    {
        let mut state=text.platform_text_system.0.0.write().unwrap();
        let db=&mut state.font_system.0;
        register(db,2,Some("Second"),true);
        register(db,3,Some("Second"),true);
        db.remove_face(id);
    }
    assert_eq!(text.all_font_names(),["Second"]);
}
#[test]
#[ignore="host font catalogue and authenticated optional bundled font fixture"]
fn real_system_font_database() {
    let mut db=Database::new();
    db.load_system_fonts();
    if let Some(path)=std::env::var_os("PROOF_NOTO") {
        let bytes=std::fs::read(path).unwrap();
        assert_eq!(bytes.len(),10_730_124);
        let faces=db.load_font_source(Source::Binary(Arc::new(bytes)));
        assert!(!faces.is_empty());
    }
    assert!(db.faces().count()>0);
    pair(db,"system");
}
