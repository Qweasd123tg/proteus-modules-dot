// Test-only module for the actual Git Graph search sites.
use super::*;
use crate::Log;
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Meter {
    calls: usize,
    bytes: usize,
    keeps: usize,
    visits: usize,
    excluded: bool,
}

thread_local! {
    static METER: Cell<Option<Meter>> = const { Cell::new(None) };
    static RENDER: Cell<Meter> = Cell::new(Meter::default());
}

fn edit(f: impl FnOnce(&mut Meter)) {
    let _ = METER.try_with(|slot| {
        if let Some(mut m) = slot.get() {
            f(&mut m);
            slot.set(Some(m));
        }
    });
}

fn record(size: usize) {
    edit(|m| {
        if !m.excluded {
            m.calls += 1;
            m.bytes += size;
        }
    });
}

pub fn non_scratch<T>(f: impl FnOnce() -> T) -> T {
    edit(|m| m.excluded = true);
    let out = f();
    edit(|m| m.excluded = false);
    out
}

pub fn predicate(f: impl FnOnce() -> bool) -> bool {
    edit(|m| m.visits += 1);
    non_scratch(f)
}

pub fn own(f: impl FnOnce() -> String) -> String {
    edit(|m| m.keeps += 1);
    f()
}

pub fn enter() {
    assert!(METER.replace(Some(Meter::default())).is_none());
}

fn leave() -> Meter {
    METER.take().unwrap()
}

pub fn rendered() {
    RENDER.set(leave());
}

struct Allocations;

unsafe impl GlobalAlloc for Allocations {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        let ptr = unsafe { System.alloc_zeroed(layout) };
        if !ptr.is_null() {
            record(layout.size());
        }
        ptr
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) };
    }

    unsafe fn realloc(&self, ptr: *mut u8, old: Layout, size: usize) -> *mut u8 {
        let ptr = unsafe { System.realloc(ptr, old, size) };
        if !ptr.is_null() {
            record(size);
        }
        ptr
    }
}

#[global_allocator]
static GLOBAL: Allocations = Allocations;

fn hash(i: usize) -> String {
    format!("{i:040x}")
}

fn rows(n: usize) -> Vec<Value> {
    (0..n).map(|i| json!({
        "hash": hash(i), "short": format!("{i:07x}"), "summary": if i+1==n {"hit tail"} else {"hit"},
        "author":"Author","email":"sample@example.invalid","time":1_700_000_000,
        "parents":[],"refs":[]
    })).collect()
}

fn contains_note(root:&Value, text:&str) -> bool {
    root.get("text").and_then(Value::as_str)==Some(text)
        || root.list("children").iter().any(|item| contains_note(item,text))
}

#[test]
fn measure_graph_match_scratch() {
    fn sample(name:&str,n:usize,query:&str,selected:Option<usize>,act:&str,want:Option<usize>,badge:Option<&str>) {
        let mut git=Git {
            graph:Some(Log {entries: into_rows(rows(n)),more:false}),
            graph_query:query.to_owned(),
            commit:selected.map(hash),
            ..Git::default()
        };
        let stats=match act {
            "render" => {
                RENDER.set(Meter::default());
                let tree=git.graph_document(&Host::default()).unwrap();
                if let Some(label)=badge {
                    assert!(tree.iter().any(|root| contains_note(root,label)), "{name}");
                }
                RENDER.take()
            }
            _ => {
                enter();
                match act {
                    "search" => git.graph_search(),
                    "previous" => git.graph_find(true),
                    "next" => git.graph_find(false),
                    _ => unreachable!(),
                }
                leave()
            }
        };
        assert_eq!(git.commit,want.map(hash),"{name}");
        let Meter {calls,bytes,keeps,visits,excluded}=stats;
        assert!(!excluded);
        println!("\nops {name} {n} {calls} {bytes} {keeps} {visits}");
        println!("answer {name} {} {}", git.commit.as_deref().unwrap_or("-"), badge.unwrap_or("-"));
    }

    sample("render-empty",0,"hit",None,"render",None,None);
    sample("render-noquery",500,"",None,"render",None,Some("0/0"));
    sample("render-single",1,"hit",Some(0),"render",Some(0),Some("1/1"));
    sample("render-hundred",100,"hit",Some(10),"render",Some(10),Some("11/100"));
    sample("render-wide",500,"hit",Some(123),"render",Some(123),Some("124/500"));
    sample("render-miss",500,"absent",Some(123),"render",Some(123),Some("0/0"));
    sample("search-first",500,"hit",None,"search",Some(0),None);
    sample("search-last",500,"tail",None,"search",Some(499),None);
    sample("search-miss",500,"absent",Some(123),"search",Some(123),None);
    sample("next-mid",500,"hit",Some(123),"next",Some(124),None);
    sample("prev-mid",500,"hit",Some(123),"previous",Some(122),None);
    sample("next-wrap",500,"hit",Some(499),"next",Some(0),None);
    sample("prev-wrap",500,"hit",Some(0),"previous",Some(499),None);
    sample("next-none",500,"hit",None,"next",Some(0),None);
    sample("prev-missing",500,"hit",Some(500),"previous",Some(499),None);

    let row = |hash: &str, s: &str| json!({"hash":hash,"summary":s});
    let duplicates = into_rows(vec![
        row("d","excluded"),row("a","fixture"),row("d","fixture"),
        row("e","fixture"),row("d","fixture"),row("f","fixture")
    ]);
    let malformed = into_rows(vec![
        row("a",""),Value::Null,json!({"hash":47}),row("",""),row("z",""),
    ]);
    let mut probe = Git {graph_query:"fixture".to_owned(),..Git::default()};
    assert_eq!(actual_matches(&probe,&duplicates),["a","d","e","d","f"]);
    probe.graph = Some(Log {entries:duplicates,more:false});
    probe.commit = Some("d".to_owned());
    probe.graph_find(false);
    assert_eq!(probe.commit.as_deref(),Some("e"));
    probe.commit = Some("d".to_owned());
    probe.graph_find(true);
    assert_eq!(probe.commit.as_deref(),Some("a"));
    probe.graph_query = "(без описания)".to_owned();
    assert_eq!(actual_matches(&probe,&malformed),["a","","","","z"]);
    probe.graph = Some(Log {entries:malformed,more:false});
    probe.graph_find(false);
    assert_eq!(probe.commit.as_deref(),Some(""));
    probe.graph_find(false);
    assert_eq!(probe.commit.as_deref(),Some("")); // next physical hit has the same hash
    probe.graph_find(true);
    assert_eq!(probe.commit.as_deref(),Some("a"));
    probe.commit = None;
    probe.graph_find(false);
    assert_eq!(probe.commit.as_deref(),Some("a"));
}
