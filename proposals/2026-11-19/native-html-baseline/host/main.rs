use gpui::{AppContext as _, Entity, TestAppContext, TestDispatcher};
use gpui_base::text::{MarkdownExtensions, MarkdownNode, SelectionFormat, TextViewState, r5_counts};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::hash::{DefaultHasher, Hash, Hasher};
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::time::Instant;

#[cfg(feature = "heap")]
mod heap;

static HOOK_HITS: AtomicUsize = AtomicUsize::new(0);
type Bodies = BTreeMap<String, String>;
type State = Entity<TextViewState>;

fn delta(a: [usize; 4], b: [usize; 4]) -> [usize; 4] {
    std::array::from_fn(|i| b[i] - a[i])
}

fn snap(state: &State, cx: &TestAppContext) -> Value {
    state.read_with(cx, |s, _| {
        let (rev, committed, selection, ready, source, plain, copy, error, ast_hash) = s.r5_snapshot();
        fn fingerprint(s: &str) -> u64 {
            let mut h = DefaultHasher::new();
            s.hash(&mut h); h.finish()
        }
        json!({
            "rev":rev,"committed":committed,"selection_rev":selection,"ready":ready,
            "source_bytes":source.len(),"source_hash":fingerprint(&source),"plain_hash":fingerprint(&plain),
            "copy_bytes":copy.len(),"copy_hash":fingerprint(&copy),"error":error,
            "document_hash":ast_hash,"plain_preview":plain.chars().take(80).collect::<String>(),
        })
    })
}

fn hook(label: &'static str, revision: u64) -> MarkdownExtensions {
    MarkdownExtensions::default().parser_revision(revision).html_inline("data-inline", move |_, _| {
        HOOK_HITS.fetch_add(1, Relaxed);
        Some(MarkdownNode::new("card", ()).text(label))
    })
}

fn proof(bodies: &Bodies, cx: &mut TestAppContext) {
    let mut rows = Vec::new();
    for (name, html) in bodies {
        let a = r5_counts();
        let state = cx.new(|cx| new_html(html, cx));
        let b = r5_counts();
        let immediate = snap(&state, cx);
        cx.run_until_parked();
        let c = r5_counts();
        let parked = snap(&state, cx);
        state.update(cx, |s, cx| {
            s.set_selection_format(SelectionFormat::Source, cx);
            s.select_all(cx);
        });
        let selected = snap(&state, cx);
        assert!(selected["copy_bytes"].as_u64().unwrap() > 0, "{name}");
        rows.push(json!({"case":name,"fg":delta(a,b),"bg":delta(b,c),"immediate":immediate,
                        "idle":parked, "selected":selected}));
    }

    for case in ["html-push-after-idle","html-push-before-idle","replace-after-short",
        "large-superseded","short-superseded","burst65","same-content","markdown-push",
        "html-config-switch","html-hook-append","html-hook-to-native","html-prefix-replace",
        "non-composable-append","non-composable-merged"] {
        let initial = match case {
            "markdown-push" => "# Old title\n\n- first\n",
            "large-superseded" => &bodies["plain-4097"],
            "short-superseded" => &bodies["plain-4095"],
            "html-config-switch" | "html-hook-append" | "html-hook-to-native" =>
                "<p>before <span data-inline='a'>plain</span> after</p>",
            "non-composable-append" | "non-composable-merged" => "<b>alpha",
            _ => "<p>A</p>",
        };
        HOOK_HITS.store(0, Relaxed);
        let a = r5_counts();
        let state = cx.new(|cx| if case == "markdown-push" {
            TextViewState::markdown(initial, cx)
        } else { new_html(initial, cx) });
        let b = r5_counts();
        let mut steps = vec![json!({"step":"create","calls":delta(a,b),"state":snap(&state,cx)})];
        macro_rules! step {
            ($name:expr, $op:expr) => {{
                let before = r5_counts();
                $op;
                steps.push(json!({"step":$name,"calls":delta(before,r5_counts()),
                                 "state":snap(&state,cx),"hook_calls_total":HOOK_HITS.load(Relaxed)}));
            }};
        }
        match case {
            "html-push-after-idle" | "html-push-before-idle" | "non-composable-append" | "non-composable-merged" => {
                if matches!(case,"html-push-after-idle"|"non-composable-append") {
                    step!("park baseline", cx.run_until_parked());
                }
                let extra = if case.starts_with("non-") { "beta</b>" } else { "<p>B</p>" };
                step!("append", state.update(cx, |s,cx| s.push_str(extra,cx)));
            }
            "replace-after-short" => {
                step!("park baseline", cx.run_until_parked());
                step!("replace", state.update(cx, |s,cx| s.set_text("<h2>Replacement</h2>",cx)));
            }
            "large-superseded" => {
                step!("replace", state.update(cx, |s,cx| s.set_text("<h2>Supersede</h2>",cx)));
            }
            "short-superseded" => {
                step!("replace", state.update(cx, |s,cx| s.set_text(&bodies["plain-4097"],cx)));
            }
            "burst65" => {
                step!("65 replacements", state.update(cx, |s,cx| {
                    for n in 0..65 { s.set_text(&format!("<b>msg {n}</b>"),cx); }
                }));
            }
            "same-content" => {
                step!("same", state.update(cx, |s,cx| {
                    for _ in 0..65 { s.set_text(initial,cx); }
                }));
            }
            "markdown-push" => {
                step!("park baseline", cx.run_until_parked());
                step!("extend markdown", state.update(cx, |s,cx| s.set_text(&(initial.to_owned()+"- next\n"),cx)));
            }
            "html-prefix-replace" => {
                step!("extend html via set_text", state.update(cx, |s,cx| s.set_text(&(initial.to_owned()+"<p>B</p>"),cx)));
            }
            "html-config-switch" | "html-hook-append" | "html-hook-to-native" => {
                step!("add hook", state.update(cx, |s,cx| s.r5_config(hook("ONE",1), cx)));
                step!("park hooked baseline", cx.run_until_parked());
                if case == "html-config-switch" {
                    step!("replace hook", state.update(cx, |s,cx| s.r5_config(hook("TWO",2),cx)));
                } else if case == "html-hook-append" {
                    step!("append", state.update(cx, |s,cx| s.push_str("<p><span data-inline='b'>tail</span></p>",cx)));
                } else {
                    step!("remove hook", state.update(cx, |s,cx| s.r5_config(MarkdownExtensions::default(),cx)));
                }
            }
            _ => unreachable!(),
        }
        step!("park final", cx.run_until_parked());
        step!("select all source", state.update(cx, |s,cx| {
            s.set_selection_format(SelectionFormat::Source,cx);
            s.select_all(cx);
        }));
        let final_state = snap(&state,cx);
        assert_eq!(final_state["rev"], final_state["committed"], "{case}");
        if case == "markdown-push" { assert_eq!(final_state["source_hash"], final_state["copy_hash"], "{case}"); }
        assert_eq!(final_state["error"], Value::Null);
        rows.push(json!({"case":case,"steps":steps}));
    }
    println!("{}", json!(rows));
}

fn batch(bodies: &Bodies, scenario: &str, runs: usize, cx: &mut TestAppContext) {
    let names: &[&str] = match scenario {
        "typical32" => &["plain-ack","plain-link","plain-escape","md-selection","md-table"],
        "edge32" => &["md-table-4096","md-links-4096"],
        "control32" => &["plain-4097"],
        "one" => &["md-selection"],
        _ => panic!("unknown scenario"),
    };
    let n = if scenario == "one" { 1 } else { 32 };
    let mut runs_out = Vec::new();
    let inputs: Vec<_> = (0..n).map(|i| bodies[names[i%names.len()]].as_str()).collect();
    for run in 0..=runs {
        let mut states = Vec::with_capacity(n);
        let a = r5_counts();
        #[cfg(feature="heap")]
        heap::start();
        let start = Instant::now();
        let mut first = 0;
        for (i, text) in inputs.iter().enumerate() {
            states.push(cx.new(|cx| new_html(text,cx)));
            if i == 0 { first = start.elapsed().as_nanos(); }
        }
        let sync = start.elapsed().as_nanos();
        let mid = r5_counts();
        cx.run_until_parked();
        let idle = start.elapsed().as_nanos();
        #[cfg(feature="heap")]
        let requested = heap::stop();
        #[cfg(not(feature="heap"))]
        let requested = [0,0];
        let last = r5_counts();
        assert!(states.iter().all(|s| s.read_with(cx, |v,_| v.is_ready())));
        if run > 0 {
            runs_out.push(json!({"first_ns":first,"sync_ns":sync,"idle_ns":idle,
                "fg":delta(a,mid),"bg":delta(mid,last),"alloc_calls_bytes":requested}));
        }
        drop(states);
        cx.run_until_parked();
    }
    println!("{}", json!(runs_out));
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    let mut cx = TestAppContext::build(TestDispatcher::new(41), Some("actual_pinned_text_state"));
    let data = std::fs::read_to_string(&args[1]).unwrap();
    let bodies: Bodies = data.lines().map(|line| {
        let x: Value = serde_json::from_str(line).unwrap();
        (x["name"].as_str().unwrap().to_owned(),x["html"].as_str().unwrap().to_owned())
    }).collect();
    match args[2].as_str() {
        "proof" => proof(&bodies,&mut cx),
        "batch" => batch(&bodies, &args[3], args[4].parse().unwrap(), &mut cx),
        _ => panic!("unknown mode"),
    }
}


// The scoped arm executes the *actual constructor expression* from RichText::new,
// copied and checked while preparing the pinned tree. This benchmark has no Window.
fn new_html(html: &str, cx: &mut gpui::Context<TextViewState>) -> TextViewState {
    #[cfg(feature="scoped")]
    { include!(concat!(env!("CARGO_MANIFEST_DIR"), "/factory.in")) }
    #[cfg(not(feature="scoped"))]
    { TextViewState::html(html, cx) }
}
