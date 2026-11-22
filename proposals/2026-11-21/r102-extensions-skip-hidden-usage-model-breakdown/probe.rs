// Test-only instrumentation of the actual Usage summary and model-grouping path.
use super::*;
use proteus_extension::{ValueExt, json};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;

#[derive(Clone, Copy, Debug, Default)]
struct Meter {
    scoped: usize,
    add: usize,
    prices: usize,
    group_calls: usize,
    group_keys: usize,
    alloc_calls: usize,
    bytes: usize,
    grouping: bool,
}

thread_local! {
    static ACTIVE: Cell<Option<Meter>> = const { Cell::new(None) };
    static LAST: Cell<Option<Meter>> = const { Cell::new(None) };
}

fn edit(f: impl FnOnce(&mut Meter)) {
    let _ = ACTIVE.try_with(|slot| {
        if let Some(mut m) = slot.get() {
            f(&mut m);
            slot.set(Some(m));
        }
    });
}

fn record(size: usize) {
    edit(|m| {
        if m.grouping {
            m.alloc_calls += 1;
            m.bytes += size;
        }
    });
}

pub fn add() { edit(|m| m.add += 1); }
pub fn price() { edit(|m| m.prices += 1); }
pub fn model_key() { edit(|m| m.group_keys += usize::from(m.grouping)); }

pub struct Group;
pub fn group() -> Group {
    edit(|m| {
        assert!(!m.grouping);
        m.grouping = true;
        m.group_calls += 1;
    });
    Group
}
impl Drop for Group {
    fn drop(&mut self) { edit(|m| m.grouping = false); }
}

pub fn summary(scoped:usize, f:impl FnOnce()->Value) -> Value {
    assert!(ACTIVE.replace(Some(Meter {scoped,..Meter::default()})).is_none());
    let value=f();
    let stats=ACTIVE.take().unwrap();
    assert!(!stats.grouping);
    assert!(LAST.replace(Some(stats)).is_none());
    value
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

fn request(i:usize,provider:&str,model:&str,turn:&str,status:&str) -> Value {
    json!({"exchange_id":format!("unit-{i:03}"),"turn_id":turn,
           "model":{"provider":provider,"model":model},"status":status,
           "usage":{"input_tokens":1000,"output_tokens":10,"cached_input_tokens":0},
           "started_at_ms":1700000000000_i64+i as i64*1000})
}

fn single(n:usize) -> Vec<Value> {
    (0..n).map(|i| request(i,"fixture","gpt-6-astra","single","completed")).collect()
}

fn mixed() -> Vec<Value> {
    let mut r:Vec<_>=(0..50).map(|i| {
        let (provider,model)=if i%2==0 {("a/b","gpt-6-astra")} else {("a","b/gpt-6-astra")};
        request(i,provider,model,"alias",if i==0 {"error"} else {"completed"})
    }).collect();
    r.push(request(50,"fixture","gpt-5.6-sol","other","completed"));
    r.push(json!({"exchange_id":"missing","model":7,"turn_id":null}));
    r
}

fn sample(name:&str,rows:Vec<Value>,selected:Option<&str>,period:&str,status:&str,expect_groups:usize) {
    let n=rows.len();
    let mut u=Usage { model:selected.map(str::to_owned),period:period.to_owned(),
                      status:status.to_owned(),..Usage::default() };
    let snap=json!({"requests":rows,"latest_turn_id":"alias"});
    let view=crate::view::render(&mut u,&snap).unwrap();
    let summary=&view[1];
    let groups=summary.list("children").iter()
        .find(|n| n.str("type")=="table")
        .map_or(0,|n| n.list("rows").len());
    assert_eq!(groups,expect_groups,"{name}");
    let Meter {scoped,add,prices,group_calls,group_keys,alloc_calls,bytes,grouping}=LAST.take().unwrap();
    assert!(!grouping);
    println!("\nops {name} {n} {scoped} {add} {prices} {group_calls} {group_keys} {alloc_calls} {bytes}");
    println!("tree {name} {summary}");
}

#[test]
fn measure_usage_grouping() {
    sample("empty",single(0),None,"all","all",0);
    sample("one",single(1),None,"all","all",0);
    sample("single-twenty",single(20),None,"all","all",0);
    sample("single-fifty",single(50),None,"all","all",0);
    sample("selected-fifty",mixed(),Some("a/b/gpt-6-astra"),"all","all",0);
    sample("selected-malformed",mixed(),Some("/"),"all","all",0);
    sample("mixed",mixed(),None,"all","all",3);
    sample("stale-filtered",mixed(),Some("stale"),"all","problems",3);
    sample("mixed-one-model-period",mixed(),None,"latest","all",0);
    sample("mixed-one-row-period",mixed(),None,"other","all",0);
    sample("invalid-period",mixed(),None,"invalid","all",0);
}
