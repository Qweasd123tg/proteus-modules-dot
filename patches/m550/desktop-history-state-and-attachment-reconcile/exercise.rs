use super::*;
use crate::{fixture::{rows,cursor}, meter::measure, domain::ImageRef};
use serde_json::json;

fn with_images(start:usize,end:usize)->Vec<AppTranscriptMessage>{
    let mut page=rows(start,end);
    for (i,row) in page.iter_mut().enumerate() {
        row.images.extend((0..4).map(|j|{
            let id=format!("img-{}-{}",start+i,j);
            ImageRef {id:id.clone(),name:id,mime_type:"image/png".into(),path:"/synthetic/image".into()}
        }));
    }
    page
}
fn evt(session_id:Uuid, stream_id:&str, seq:u64, start:usize, count:usize, history:Option<AppTranscriptCursor>) -> AppServerEvent {
    AppServerEvent::SessionSnapshot{snapshot:Box::new(AppSessionSnapshot {
        session_id, stream_id:stream_id.into(), seq, root_thread_id:None,
        transcript:with_images(start,start+count),history,execution:Default::default()
    })}
}
fn route(chat:&mut Chat, cx:&mut Context<Chat>, tag:&str, event:AppServerEvent, accepted:bool,
         count:usize, snapshot:bool, expected:Option<HistoryRange>, archived:bool) {
    cx.calls.clear();
    let before_prune=crate::images::shared().0;
    let (shown,_)=measure(||chat.apply_event(event,cx));
    assert_eq!(shown,accepted);
    assert_eq!(chat.display_transcript().entries().len(),count);
    assert_eq!(chat.history.archived(),archived);
    if !accepted {
        assert!(cx.calls.is_empty());
        println!("ROUTE {}",json!({"tag":tag,"runs":0,"normalized":"[]","prunes":0,"telemetry":chat.scroller.telemetry()}));
        return;
    }
    let base:Vec<_>=cx.calls.iter().enumerate().filter_map(|(i,c)|match c {Call::Range(range,seek)=>Some((i,*range,*seek)),_=>None}).collect();
    assert!(!base.is_empty());
    for (_,range,seek) in &base {assert_eq!((*range,*seek),(expected,false));}
    let n=base.len();
    assert_eq!(n, if snapshot && !cfg!(feature="range_candidate"){2}else{1},"{tag}");
    let mut normalized=std::mem::take(&mut cx.calls);
    if n==2 {
        let i=base[1].0;
        assert_eq!(normalized[i-1],Call::Update);
        assert_eq!(normalized[i-2],Call::Notify);
        normalized.drain(i-1..=i);
    }
    if snapshot {assert!(normalized.contains(&Call::Context));}
    else {assert!(!normalized.contains(&Call::Context));}
    println!("ROUTE {}",json!({"tag":tag,"runs":n,"normalized":format!("{normalized:?}"),
                              "prunes":crate::images::shared().0-before_prune,"telemetry":chat.scroller.telemetry()}));
    cx.calls=normalized;
}

#[test]
fn restore_boot_active_archived_and_empty() {
    let id=Uuid::from_u128(9);
    let mut chat=Chat::new("/synthetic/чат".into());
    let mut cx=Context::default();cx.calls.reserve(100);
    chat.session.cursor.begin_connection();
    let initial=HistoryRange{start:49950,rows:50,total:50000};
    let c=cursor("ревизия0",49950);
    crate::images::stage_retired();
    route(&mut chat,&mut cx,"first",evt(id,"ready",0,49950,50,Some(c.clone())),true,50,true,Some(initial),false);
    assert_eq!(crate::images::shared().1,0);
    assert!(chat.sent_images.by_id.is_empty());
    assert_eq!(chat.scroller.telemetry().0,1);
    let key=chat.scroller.state.as_ref().unwrap().height_key.clone().unwrap();
    assert_eq!(key.identity,scroller::height_hash(format!("chat:/synthetic/чат:{id}")));
    assert_eq!(key.revision,scroller::height_hash("ревизия0"));
    assert_eq!(key.prefix,49949);
    route(&mut chat,&mut cx,"duplicate",evt(id,"ready",0,49950,50,Some(c.clone())),false,50,true,Some(initial),false);
    route(&mut chat,&mut cx,"foreign-stream",evt(id,"wrong",1,49950,50,Some(c.clone())),false,50,true,Some(initial),false);
    route(&mut chat,&mut cx,"non-snapshot",AppServerEvent::ExecutionUpdated{execution:Default::default()},true,50,false,Some(initial),false);
    // Preserve an exact native splice and the visible reading anchor on a same-revision refresh.
    let request=chat.history.request(Direction::Older,&chat.session.transcript).unwrap();
    let archived_range=HistoryRange{start:49900,rows:100,total:50000};
    let older=AppTranscriptPage{revision:c.revision.clone(),start:49900,total:50000,messages:with_images(49900,49950),base:None};
    let changes=chat.history.accept_page(&chat.session.transcript,Direction::Older,&request,older,12..19).unwrap();
    chat.apply_history_changes(changes,&mut cx);
    assert_eq!(chat.history.range(&chat.session.transcript),Some(archived_range));
    let seek=chat.history.begin_request().unwrap();
    route(&mut chat,&mut cx,"archived-retained",evt(id,"ready",1,49950,50,Some(c.clone())),true,100,true,Some(archived_range),true);
    assert!(cx.calls.contains(&Call::Cancel));
    assert!(!chat.history.finish_request(seek));
    assert!(matches!(chat.display_transcript().entries()[0].text.as_ref(),"row 49900"));
    // New revision truncates archive inside the common prefix and invalidates its tail.
    let mut reduced=cursor("ревизия1",49929);
    reduced.base=Some(AppTranscriptBase{revision:c.revision,common_prefix:49925});
    let shrunk=HistoryRange{start:49900,rows:25,total:49930};
    chat.scroller.state.as_ref().unwrap().bar.waiting(49990,true);
    route(&mut chat,&mut cx,"rewritten",evt(id,"ready",2,49929,1,Some(reduced)),true,25,true,Some(shrunk),true);
    assert_eq!(chat.scroller.telemetry(),(3,1,0,1,false,None));
    // A reconnect to an empty untargetable baseline keeps the range/key clear.
    chat.session.cursor.begin_connection();
    route(&mut chat,&mut cx,"empty",evt(id,"next",0,0,0,None),true,0,true,None,false);
    assert!(chat.scroller.state.as_ref().unwrap().height_key.is_none());
}

#[test]
fn cold_image_ids_do_not_change_shared_pruning_or_warm_membership() {
    let mut t=Transcript::default();t.reset(with_images(49950,50000));
    let mut empty=SentImages::default();
    crate::images::stage_retired();
    let before=crate::images::shared().0;
    let (_,cold)=measure(||empty.retain(t.entries()));
    assert!(empty.by_id.is_empty());
    assert_eq!(crate::images::shared(),(before+1,0));
    assert_eq!(cold.requests==0,cfg!(feature="images_candidate"));
    let mut warm=SentImages::default();
    warm.by_id.insert("img-49950-0".into(),11);
    warm.by_id.insert("img-49999-3".into(),47);
    warm.by_id.insert("never-in-page".into(),99);
    crate::images::stage_retired();
    let (_,resident)=measure(||warm.retain(t.entries()));
    assert_eq!(crate::images::shared(),(before+2,0));
    assert_eq!(warm.by_id.len(),2);
    assert_eq!(warm.by_id["img-49950-0"],11);
    assert_eq!(warm.by_id["img-49999-3"],47);
    assert!(!warm.by_id.contains_key("never-in-page"));
    println!("IMAGE {}",json!({"entries":50,"ids":200,"cold_requests":cold.requests,"cold_bytes":cold.bytes,
                               "warm_requests":resident.requests,"warm_bytes":resident.bytes}));
}

#[test]
fn native_range_setter_waiting_pin_and_empty() {
    let bar=scroller::HistoryScrollbar::default();
    let first=HistoryRange{start:440,rows:50,total:500};
    assert!(bar.set_range(Some(first),true));
    bar.waiting(455,false);
    assert!(!bar.set_range(Some(first),false));
    assert_eq!(bar.telemetry(),(1,0,0,0,false,Some(455)));
    assert!(!bar.set_range(Some(first),false));
    assert_eq!(bar.telemetry(),(1,0,0,0,false,Some(455)));
    bar.waiting(460,false);
    let moved=HistoryRange{start:500,rows:40,total:600};
    assert!(bar.set_range(Some(moved),false));
    assert!(!bar.set_range(Some(moved),false));
    assert_eq!(bar.telemetry(),(2,0,1,0,false,None));
    assert!(bar.set_range(None,false));
    assert!(!bar.set_range(None,false));
    assert_eq!(bar.telemetry(),(3,0,0,0,false,None));
}
