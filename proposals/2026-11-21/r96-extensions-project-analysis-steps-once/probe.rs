// Test-only hooks instrument the actual step-list path, not the request or whole page.
use crate::{Analysis, facts};
use proteus_extension::{Value, ValueExt, json};
use std::cell::Cell;
use std::hint::black_box;

#[derive(Clone, Copy, Default)]
struct Counts {
    histogram: usize,
    status: usize,
    query_folds: usize,
    titles: usize,
    hook_visits: usize,
    matched_scratch: usize,
    drawn: usize,
}

thread_local! { static COUNTS: Cell<Counts> = Cell::new(Counts::default()); }

fn adjust(change: impl FnOnce(&mut Counts)) {
    COUNTS.with(|slot| {
        let mut counts=slot.get();
        change(&mut counts);
        slot.set(counts);
    });
}

pub(crate) fn histogram_kind(step: &Value) -> &str {
    adjust(|c| c.histogram+=1);
    facts::kind(step)
}
pub(crate) fn status_call() { adjust(|c| c.status+=1); }
pub(crate) fn title_call() { adjust(|c| c.titles+=1); }
pub(crate) fn hook_visit() { adjust(|c| c.hook_visits+=1); }
pub(crate) fn fold(query: &str) -> String {
    adjust(|c| c.query_folds+=1);
    query.trim().to_lowercase()
}
#[allow(dead_code)] // Only the baseline materializes matching references.
pub(crate) fn scratch(len: usize) { adjust(|c| c.matched_scratch=len); }
pub(crate) fn drawn() { adjust(|c| c.drawn+=1); }

fn fixture(n: usize) -> Vec<Value> {
    (0..n).map(|i| {
        let data = match i%4 {
            0 => json!({"kind":"model","origin":"direct","request":{"model":{"model":"synthetic-model"}},
                        "response":(i%8==0).then(|| json!({"finish_reason":"Stop"}))}),
            1 => json!({"kind":"tool","call":{"name": "ПРОВЕРКА 🦀"},"result":{"ok":i%8==1}}),
            2 => json!({"kind":"compaction","report":{"changed":i%8==2}}),
            _ => {
                let failure = match i%16 { 3=>Some(0), 11=>Some(11), _=>None };
                let nested:Vec<_>=(0..12).map(|j| json!({"outcome":{
                    "status": if failure==Some(j) {"failed"} else {"accepted"}}})).collect();
                json!({"kind":"hook","trace":{"input":{"event":{"event":"before_tool"}},"steps":nested}})
            }
        };
        json!({"sequence":i*2+1,"started_at_ms":i*1000,"finished_at_ms":i*1000+100,"data":data})
    }).collect()
}

#[test]
fn measure_analysis_step_list_production_visits() {
    for (case,n,kind,problems,query) in [
        ("empty",0,"all",false," nonempty "),
        ("one",1,"all",false," model "),
        ("cap",401,"all",false,""),
        ("all",420,"all",false,""),
        ("white",420,"all",false," \t"),
        ("miss",420,"all",false,"not found"),
        ("unicode",420,"tool",false,"  пРоВеРкА 🦀\t "),
        ("problems",420,"all",true,""),
        ("problem-query",420,"tool",true," пРоВеРкА 🦀 "),
        ("hook-query",420,"hook",true,"ИНСТРУМЕНТОМ"),
        ("selected-zero",17,"hook",false,""),
    ] {
        let mut steps=fixture(n);
        if case=="selected-zero" {
            for step in &mut steps {
                if facts::kind(step)=="hook" {
                    step["data"]["kind"]=Value::Bool(false);
                }
            }
        }
        let panel=Analysis {
            kind:kind.to_owned(), problems, query:query.to_owned(),
            step:Some(3), ..Analysis::default()
        };
        COUNTS.set(Counts::default());
        let tree=black_box(panel.step_list(black_box(&steps)));
        let Counts{histogram,status,query_folds,titles,hook_visits,matched_scratch,drawn}=COUNTS.get();
        assert_eq!(tree.str("type"),"stack");
        println!("\nops {case} {n} {histogram} {status} {query_folds} {titles} {hook_visits} {matched_scratch} {drawn}");
        println!("tree {case} {}",serde_json::to_string(&tree).unwrap());
    }
}
