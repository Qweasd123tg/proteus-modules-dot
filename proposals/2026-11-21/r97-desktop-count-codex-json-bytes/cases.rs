use serde_json::json;

fn values() -> Vec<Value> {
    let mut map = serde_json::Map::new();
    map.insert("z".into(),json!({"x":[null, 42]}));
    map.insert("a".into(),json!("🙂\u{0000}"));
    let mut cases = vec![
        Value::Null, json!(true), json!(false), json!(i64::MIN), json!(u64::MAX),
        json!(-0.0_f64), json!(4.2e-270_f64), json!(3.4e275_f64), json!(""),
        json!("é雪🦀/&\"\\\n\u{0008}\u{000c}\r\t"), Value::Array(vec![]), json!({}), Value::Object(map),
        json!(["line1\n", {"число":"七","array":[true,false,null,"a\u{001f}z"]}]),
    ];
    cases.push(json!((0..=31u8).map(char::from).collect::<String>()));
    cases
}
fn pending(params: Value)->Event {
    Event::PendingRequest {id:json!("req/opaque"),method:"example/input".into(),params}
}
fn sample_tool(input:Value,output:&str)->Item {
    Item {id:"item".into(), turn_id:"turn".into(), status:"completed".into(),
        timestamp_ms:Some(9),kind:crate::ItemKind::Tool {name:"fixture".into(),input,output:output.into()}}
}
fn raw_request(id:&str,params:Value)->RawEvent {
    RawEvent::Request {id:json!(id),method:"example/input".into(),params}
}
#[test]
fn exact_counts_through_real_event_and_item_types() {
    let cases=values();
    let output="é\n🦀";
    let mut sizes=Vec::new();
    for v in &cases {
        let json=v.to_string().len();
        for event in [pending(v.clone()),Event::Plan(v.clone()),Event::Usage(v.clone())] {
            assert_eq!(event_bytes(&event),json+1024);
        }
        let tool=sample_tool(v.clone(), output);
        assert_eq!(item_bytes(&tool),json+output.len()+1024);
        assert_eq!(event_bytes(&Event::ItemUpsert(tool)),json+output.len()+1024);
        sizes.push(json);
    }
    let text="界\n";
    let tool=sample_tool(cases.last().unwrap().clone(), output);
    let ordinary=projection::item(&json!({"id":"m","type":"agentMessage","text":text}),"t",false,None).unwrap();
    assert_eq!(item_bytes(&ordinary),text.len()+512);
    let expected=sizes.last().unwrap()+output.len()+1024+text.len()+512+1024;
    assert_eq!(event_bytes(&Event::Resynced {current_turn:Some("ignored".into()),history:vec![tool, ordinary]}),expected);
    let delta=projection::notification("item/agentMessage/delta",&json!({"delta":text})).unwrap();
    assert_eq!(event_bytes(&delta),512+text.len());
    assert_eq!(event_bytes(&Event::ResyncStarted),1024);
    eprintln!("TRACE values={} sizes={sizes:?} mixed_history={expected} text_delta={}",cases.len(),512+text.len());
}
#[test]
fn routed_payload_order_replay_and_rejection() {
    let params=json!({"threadId":"chat","field":"é\n"});
    let plan=projection::notification("turn/plan/updated",&params).unwrap();
    let usage=projection::notification("thread/tokenUsage/updated",&params).unwrap();
    let request=Event::PendingRequest {id:json!("request:a/b"),method:"example/input".into(),params:params.clone()};
    let item_wire=json!({"threadId":"chat","turnId":"t","startedAtMs":99,
        "item":{"type":"dynamicToolCall","tool":"notes","id":"entry","arguments":{"x":[true,"雪\n"]},"result":"line1\nline2"}});
    let item=projection::notification("item/started",&item_wire).unwrap();
    let input=json!({"x":[true,"雪\n"]});
    assert!(matches!(&item,Event::ItemUpsert(Item {kind:crate::ItemKind::Tool {input:i,output,..},timestamp_ms:Some(99),..})
        if *i==input && output==&json!("line1\nline2").to_string()));
    let ordinary=params.to_string().len()+1024;
    let tool_bytes=input.to_string().len()+json!("line1\nline2").to_string().len()+1024;
    assert_eq!(event_bytes(&item),tool_bytes);
    let mut r=Router::default();
    r.starting=1;
    assert_eq!(r.raw(raw_request("request:a/b",params.clone())),None);
    assert_eq!(r.raw(RawEvent::Notification{method:"turn/plan/updated".into(),params:params.clone()}),None);
    assert_eq!(r.early_bytes,ordinary*2);
    let (events,_,_)=r.register("chat").unwrap();
    assert!(r.finish_start().is_empty());
    assert_eq!(r.early_bytes,0);
    assert_eq!(r.budget.load(Ordering::Acquire),ordinary*2);
    assert_eq!(r.raw(RawEvent::Notification{method:"thread/tokenUsage/updated".into(),params}),None);
    assert_eq!(r.raw(RawEvent::Notification{method:"item/started".into(),params:item_wire}),None);
    let total=ordinary*3+tool_bytes;
    assert_eq!(r.budget.load(Ordering::Acquire),total);
    for expected in [request,plan,usage,item] {assert_eq!(events.try_recv().unwrap(),expected);}
    assert_eq!(r.budget.load(Ordering::Acquire),0);
    assert_eq!(r.raw(raw_request("no-route",json!({"threadId":"unopened"}))),Some(json!("no-route")));
    let (other,_,_)=r.register("temp").unwrap();
    r.deliver("temp",Event::Plan(json!(null)));
    assert_eq!(r.budget.load(Ordering::Acquire),1028);
    r.disconnect_thread("temp","fixture done".into());
    drop(other);
    assert_eq!(r.budget.load(Ordering::Acquire),0);
    eprintln!("TRACE replay=request,plan direct=usage,tool bytes={total} drained=0 dropped=0 no_route=opaque");
}
#[test]
fn exact_headroom_and_one_byte_over() {
    let params=json!({"threadId":"edge","note":"🙂\n"});
    let size=params.to_string().len()+1024;
    for excess in [0,1] {
        let seed=MAX_QUEUED_BYTES-size+excess;
        let mut early=Router::default();
        early.starting=1;
        early.early_bytes=seed;
        let rejection=early.raw(raw_request("edge-id",params.clone()));
        if excess==0 {
            assert!(rejection.is_none());
            assert_eq!(early.early_bytes,MAX_QUEUED_BYTES);
            assert_eq!(early.early.len(),1);
            assert_eq!(early.finish_start(),vec![json!("edge-id")]);
        } else {
            assert_eq!(rejection,Some(json!("edge-id")));
            assert!(!early.is_connected());
            assert!(early.early.is_empty());
        }
        assert_eq!(early.early_bytes,0);
        let mut routed=Router::default();
        let (events,_,generation)=routed.register("edge").unwrap();
        routed.budget.store(seed,Ordering::Release);
        routed.deliver("edge",Event::Usage(params.clone()));
        if excess==0 {
            assert!(routed.contains_generation("edge",generation));
            assert_eq!(routed.budget.load(Ordering::Acquire),MAX_QUEUED_BYTES);
            assert_eq!(events.try_recv().unwrap(),Event::Usage(params.clone()));
        } else {
            assert!(!routed.contains_generation("edge",generation));
            assert!(events.is_closed());
            assert!(events.try_recv().is_err());
            assert!(events.disconnect_reason().is_some());
        }
        assert_eq!(routed.budget.load(Ordering::Acquire),seed);
    }
    eprintln!("TRACE event={size} early_and_direct=exact-accepted,plus-one-rejected");
}
#[test]
fn transient_sink_during_count_only() {
    let arm=env!("R97_ARM");
    let candidate=arm.contains("/candidate/");
    let large=json!({"body":"значение🦀\n\\\"".repeat(3600), "tail":[null,true,1234]});
    let bytes=large.to_string().len();
    let tool=sample_tool(large.clone(),"ok");
    let examples=[
        ("small-plan",Event::Plan(json!({"step":1})),1034,true),
        ("large-params",pending(large),bytes+1024,true),
        ("tool-input",Event::ItemUpsert(tool.clone()),bytes+2+1024,true),
        ("resync-2",Event::Resynced {current_turn:None,history:vec![tool.clone(),tool]},2*(bytes+2+1024)+1024,true),
        ("delta",Event::TextDelta {id:"i".into(),turn_id:"t".into(),delta:"é".into()},514,false),
    ];
    for (label,event,want,formats) in examples {
        let (count,calls,allocated)=crate::measurement(||event_bytes(std::hint::black_box(&event)));
        assert_eq!(count,want);
        if !formats || candidate {assert_eq!((calls,allocated),(0,0));}
        else {assert!(calls>0 && allocated>0);}
        eprintln!("WORK {label} count={count} alloc_or_realloc_calls={calls} requested_bytes={allocated}");
    }
    eprintln!("ARM {arm}");
    eprintln!("TRACE measured_payload_json={bytes} fixtures=5");
}
