// Test-only module. Meter enabled only across the actual request-number table site.
use super::*;
use proteus_extension::{json, ValueExt};
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;


thread_local! {
    static METER: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

fn record(size: usize) {
    let _ = METER.try_with(|meter| {
        if let Some((calls, bytes)) = meter.get() {
            meter.set(Some((calls + 1, bytes + size)));
        }
    });
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

thread_local! {
    static RAW: Cell<usize> = const { Cell::new(0) };
    static PAGE: Cell<usize> = const { Cell::new(0) };
    static DONE: Cell<Option<[usize; 6]>> = const { Cell::new(None) };
}
pub fn raw_key(request: &Value) -> &str {
    RAW.set(RAW.get()+1);
    request.str("exchange_id")
}
pub fn page_key(request: &Value) -> &str {
    PAGE.set(PAGE.get()+1);
    request.str("exchange_id")
}
pub fn begin() {
    RAW.set(0);
    PAGE.set(0);
    METER.with(|c| assert!(c.replace(Some((0,0))).is_none()));
}
pub fn end(len: usize, cap: usize) {
    let (calls,bytes)=METER.with(|c| c.take().unwrap());
    DONE.set(Some([len,cap,calls,bytes,RAW.get(),PAGE.get()]));
}

#[test]
fn measure_request_number_table() {
    let input = |n:usize| (0..n).map(|i| json!({
        "exchange_id":format!("id-{i:04}"),"turn_id":"show","started_at_ms":i
    })).collect::<Vec<_>>();
    fn sample(name:&str, rows:Vec<Value>, page:i64, query:&str, order:&str, period:&str, expected:&[usize]) {
        let n=rows.len();
        let snapshot=json!({"requests":rows});
        let mut usage=Usage{page,query:query.into(),order:order.into(),period:period.into(),..Usage::default()};
        let view=crate::view::render(&mut usage,&snapshot).unwrap();
        let [len,cap,calls,bytes,raw_reads,page_reads]=DONE.take().unwrap();
        let rendered:Vec<_>=view.iter()
            .map(|node| &node["children"][0]["children"][0])
            .filter(|b| b.str("action")=="request")
            .map(|b| {
                let label=b.str("label");
                let ord:usize=label.split('#').nth(1).unwrap().split(' ').next().unwrap().parse().unwrap();
                (ord,b.get("value").unwrap())
            }).collect();
        assert!(rendered.iter().map(|(ord,_)| *ord).eq(expected.iter().copied()),"{name}: {rendered:?}");
        println!("\nops {name} {n} {} {len} {cap} {calls} {bytes} {raw_reads} {page_reads}",rendered.len());
        println!("tree {name} {}",json!({"buttons":rendered}));
    }
    let range=|a,b|(a..=b).collect::<Vec<usize>>();
    sample("empty",input(0),0,"","oldest","all",&[]);
    sample("one",input(1),0,"","oldest","all",&[1]);
    sample("twenty",input(20),0,"","oldest","all",&range(1,20));
    sample("over-head",input(21),0,"","oldest","all",&range(1,20));
    sample("over-tail",input(21),1,"","oldest","all",&[21]);
    sample("long-head",input(2000),0,"","oldest","all",&range(1,20));
    sample("long-tail",input(2000),99,"","oldest","all",&range(1981,2000));
    sample("long-newest",input(2000),0,"","newest","all",&(1981..=2000).rev().collect::<Vec<_>>());
    sample("long-miss",input(2000),0,"absent","oldest","all",&[]);
    sample("long-one",input(2000),0,"id-1999","oldest","all",&[2000]);
    let mut odd=input(45);
    for (i,r) in odd.iter_mut().enumerate() {
        if i>=6 {r["turn_id"]=json!("hide");}
    }
    for i in [0,1,42] {odd[i]["exchange_id"]=json!("dup");}
    for i in [2,44] {odd[i].as_object_mut().unwrap().remove("exchange_id");}
    odd[3]["exchange_id"]=Value::Null;
    odd[4]["exchange_id"]=json!(17);
    odd[5]["exchange_id"]=json!("");
    sample("duplicates",odd,0,"","oldest","show",&[43,43,45,45,45,45]);
}
