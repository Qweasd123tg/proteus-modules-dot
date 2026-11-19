use gpui::{AppContext as _, TestAppContext, TestDispatcher};
use gpui_base::text::{TextViewState,r5_counts};
use serde_json::{Value,json};

fn html_factory(html: &str, cx: &mut gpui::Context<TextViewState>) -> TextViewState {
    #[cfg(feature = "scoped")]
    { include!(concat!(env!("CARGO_MANIFEST_DIR"),"/factory.in")) }
    #[cfg(not(feature = "scoped"))]
    { TextViewState::html(html,cx) }
}

fn main() {
    let path = std::env::args().nth(1).unwrap();
    let corpus = std::fs::read_to_string(path).unwrap();
    let mut cx = TestAppContext::build(TestDispatcher::new(41),Some("explicit_push"));
    let mut out = Vec::new();
    for line in corpus.lines() {
        let case: Value = serde_json::from_str(line).unwrap();
        let name = case["name"].as_str().unwrap();
        if !["md-selection","md-table-4096","plain-4097"].contains(&name) { continue; }
        let text = case["html"].as_str().unwrap();
        let tail = "<p>Tail</p>";
        let a = r5_counts();
        let state = cx.new(|cx| html_factory(text,cx));
        let b = r5_counts();
        cx.run_until_parked();
        let c = r5_counts();
        state.update(&mut cx,|s,cx| s.push_str(tail,cx));
        let d = r5_counts();
        cx.run_until_parked();
        let e = r5_counts();
        let (rev,committed,_,ready,source,_,_,err,ast) = state.read_with(&cx,|s,_| s.r5_snapshot());
        assert_eq!(rev,committed);
        assert!(ready && err.is_none());
        assert_eq!(source,format!("{text}{tail}"));
        let delta = |x:[usize;4],y:[usize;4]| [y[0]-x[0],y[1]-x[1]];
        out.push(json!({"name":name,"sync":delta(a,b),"before_append_worker":delta(b,c),
            "append_sync":delta(c,d),"append_worker":delta(d,e),"ast":ast}));
    }
    println!("{}",json!(out));
}
