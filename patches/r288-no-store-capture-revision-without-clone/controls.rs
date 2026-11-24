// Independent equality contract proof, using the pinned concrete DTOs.
// No float witness is constructed through JSON.
use proteus_contracts::{
    domain::{
        Citation, ContextChunk, FileSearchResult, HostedToolActivity, ImageRef, Patch, ToolCall,
        ToolResult,
    },
    model_standard::{CanonicalMessage, ContentPart, MessagePhase, MessageRole},
};
use serde_json::{Value, json};
use std::{ffi::OsString, hint::black_box, os::unix::ffi::OsStringExt, path::PathBuf};

fn old(h: &Vec<CanonicalMessage>) -> bool {
    let previous = h.clone();
    black_box(&previous);
    h != &previous
}
fn proposed(h: &[CanonicalMessage]) -> bool {
    h.iter().any(|m| !m.eq(m))
}
fn compare(h: &Vec<CanonicalMessage>, expected: bool) {
    assert_eq!(old(h), expected);
    assert_eq!(proposed(h), expected);
}
fn msg(part: ContentPart) -> CanonicalMessage {
    CanonicalMessage::new(MessageRole::Assistant, vec![part])
        .with_phase(MessagePhase::Commentary)
        .with_name("δοκιμή")
        .with_tool_call_id("proof".into())
        .with_metadata(json!({"z":[1,false,{"æ":"\n🦀"}],"a":0.25}))
}
fn context(bits: u32) -> ContentPart {
    ContentPart::Context {
        chunk: ContextChunk::new("source", "текст")
            .with_path("/path/κ".into())
            .with_score(f32::from_bits(black_box(bits)))
            .with_metadata(json!({"packed":[null,true]})),
    }
}
fn hosted(bits: u64) -> ContentPart {
    let mut activity: HostedToolActivity = serde_json::from_value(json!({
       "kind":"file_search","id":"typed","status":{"state":"completed"},"queries":["q"],"results":[]
    }))
    .unwrap();
    let HostedToolActivity::FileSearch { results, .. } = &mut activity else {
        unreachable!()
    };
    *results = vec![
        FileSearchResult::new("first", None, Some(1.0), Some("先".into()), Value::Null),
        FileSearchResult::new(
            "second",
            Some("filename".into()),
            Some(f64::from_bits(black_box(bits))),
            Some("nested".into()),
            json!({"range":[0,12]}),
        ),
    ];
    ContentPart::HostedToolActivity { activity }
}
fn context_bits(m: &CanonicalMessage) -> u32 {
    let ContentPart::Context { chunk } = &m.parts[0].payload else {
        unreachable!()
    };
    chunk.score.unwrap().to_bits()
}
fn hosted_bits(m: &CanonicalMessage) -> u64 {
    let ContentPart::HostedToolActivity {
        activity: HostedToolActivity::FileSearch { results, .. },
    } = &m.parts[0].payload
    else {
        unreachable!()
    };
    results[1].score.unwrap().to_bits()
}
pub(crate) fn equality_controls() {
    let text_bad = PathBuf::from(OsString::from_vec(vec![b'/', b'x', 0xff, 0x80]));
    let ordinary=vec![
    ("image",ContentPart::Image{image:ImageRef{id:"fixture-image".into(),name:"image".into(),mime_type:"image/png".into(),path:text_bad.clone()}}),
    ("text",ContentPart::Text{text:"Привет\u{0}世界".into()}),
    ("context",context(0x3f800000)),
    ("file",ContentPart::FileRef{path:text_bad,content:Some("෴".into())}),
    ("call",ContentPart::ToolCall{call:ToolCall::new("id","test",json!({"order":["z","a"]})).with_raw_arguments("raw args")}),
    ("result",ContentPart::ToolResult{result:ToolResult::ok("id".into(),"result").with_metadata(json!({"proof":[true,0,{"text":"α"}]}))}),
    ("patch",ContentPart::Patch{patch:Patch::new("synthetic patch text")}),
    ("summary",ContentPart::ReasoningSummary{text:"summary".into()}),
    ("reasoning",ContentPart::Reasoning{text:"reason".into(),signature:Some("signature".into())}),
    ("opaque",ContentPart::Opaque{format:"opaque".into(),data:json!([null,{"noncanonical":["a",0.0]}])}),
    ("hosted-file",hosted(0x3ff0000000000000)),
    ("hosted-web",ContentPart::HostedToolActivity{activity:serde_json::from_value(json!({"kind":"web_search","id":"typed-web","status":{"state":"completed"},"action":{"type":"search","queries":["subject"],"sources":[]}})).unwrap()}),
    ("citation",ContentPart::Citation{citation:serde_json::from_value::<Citation>(json!({"type":"url","start_index":1,"end_index":2,"title":"test title","url":"https://example.com"})).unwrap()}),
 ];
    let names = ordinary.iter().map(|(s, _)| *s).collect::<Vec<_>>();
    let basic = ordinary
        .into_iter()
        .map(|(_, p)| msg(p))
        .collect::<Vec<_>>();
    compare(&vec![], false);
    for m in &basic {
        compare(&vec![m.clone()], false);
    }
    compare(&basic, false);
    let mut f32_cases = vec![];
    let mut f64_cases = vec![];
    for (bits, nan) in [
        (0x00000000, false),
        (0x80000000, false),
        (0x7f800000, false),
        (0xff800000, false),
        (0x3f054321, false),
        (0x7fc12345, true),
        (0xffc12345, true),
        (0x7f812345, true),
        (0xff812345, true),
    ] {
        let witness = msg(context(bits));
        assert_eq!(context_bits(&witness), bits);
        assert_eq!(context_bits(&witness.clone()), bits);
        compare(&vec![witness.clone()], nan);
        let mut mixed = basic.clone();
        mixed.insert(3, witness);
        compare(&mixed, nan);
        assert_eq!(context_bits(&mixed[3]), bits);
        f32_cases.push(json!({"bits":format!("{bits:08x}"),"old_and_new_changed":nan}));
    }
    for (bits, nan) in [
        (0x0000000000000000, false),
        (0x8000000000000000, false),
        (0x7ff0000000000000, false),
        (0xfff0000000000000, false),
        (0x3ff00123456789ab, false),
        (0x7ff80123456789ab, true),
        (0xfff80123456789ab, true),
        (0x7ff00123456789ab, true),
        (0xfff00123456789ab, true),
    ] {
        let witness = msg(hosted(bits));
        assert_eq!(hosted_bits(&witness), bits);
        assert_eq!(hosted_bits(&witness.clone()), bits);
        compare(&vec![witness.clone()], nan);
        let mut mixed = basic.clone();
        mixed.push(witness);
        compare(&mixed, nan);
        assert_eq!(hosted_bits(mixed.last().unwrap()), bits);
        f64_cases.push(json!({"bits":format!("{bits:016x}"),"old_and_new_changed":nan}));
    }
    println!(
        "{}",
        json!({"case":"typed-equality","part_shapes":names,"f32":f32_cases,"f64":f64_cases,"passed":true})
    );
}
