// Test-only instrumentation of actual Files Listing::parse, never installed.
use super::*;
use proteus_extension::json;
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

fn fixture(folder:&str,n:usize) -> Value {
    let entries=(0..n).map(|i| {
        let name=format!("fixture-report-{i:03}-data-данные.rs");
        let path=format!("{folder}/{name}");
        json!({"path":path,"name":name,"kind":"file"})
    }).collect::<Vec<_>>();
    let response=json!({"path":folder,"entries":entries,"truncated":false});
    let raw=serde_json::to_vec(&response).unwrap();
    serde_json::from_slice(&raw).unwrap()
}

fn sample(name:&str,value:Value) {
    let raw=value.list("entries");
    let n=raw.len();
    let input=raw.iter().filter(|entry| !EXCLUDED.contains(&entry.str("name"))).map(|entry| {
        let text=entry.str("path");
        let eligible = matches!(entry.get("path"),Some(Value::String(s)) if
            s.capacity()==s.len() && !s.starts_with("./") && !s.is_empty());
        (text.as_ptr(),eligible,text.len(),text.trim_start_matches("./").to_owned())
    }).collect::<Vec<_>>();
    let eligible=input.iter().filter(|e| e.1).count();
    let eligible_bytes=input.iter().filter(|e| e.1).map(|e|e.2).sum::<usize>();
    assert!(METER.replace(Some((0,0))).is_none());
    let listing=admit(value);
    let (calls,bytes)=METER.take().unwrap();
    let entries=&listing.entries;
    assert_eq!(entries.len(),input.len());
    let mut moved=0;
    for (e,(ptr,eligible,_,expected)) in entries.iter().zip(&input) {
        assert_eq!(e.path, *expected);
        if *eligible && e.path.as_ptr()==*ptr {
            moved+=1;
        }
        assert_eq!(e.path.capacity(),e.path.len());
    }
    let path_bytes=entries.iter().map(|e|e.path.len()).sum::<usize>();
    let path_cap=entries.iter().map(|e|e.path.capacity()).sum::<usize>();
    let row_slot=std::mem::size_of::<Entry>();
    println!("\nops {name} {n} {} {path_bytes} {path_cap} {row_slot} {} {eligible} {eligible_bytes} {moved} {calls} {bytes}",
             entries.len(), entries.capacity());
    let rows=entries.iter().map(|entry| json!([entry_name(entry),entry.path,format!("{:?}",entry.kind)])).collect::<Vec<_>>();
    println!("tree {name} {}",json!({"rows":rows,"truncated":listing.truncated}));
}

#[test]
fn measure_listing_path_move() {
    sample("absent",json!("not a listing"));
    sample("empty",fixture("ordinary",0));
    sample("one",fixture("ordinary",1));
    sample("ordinary-small",fixture("ordinary/nested",32));
    sample("ordinary",fixture("ordinary",64));
    let mut mixed:Value=serde_json::from_str(r#"{"entries":[
       {"name":"escaped","path":"dir/\u65e5\u672c.rs","kind":"file"},
       {"name":"Alias","path":"dir/ordinary.rs","kind":"file"},
       {"name":"slash","path":".//nested//./has\\literal.rs","kind":"symlink"},
       {"name":"loose","path":"replace","kind":"unknown"},
       {"name":".git","path":"ordinary-but-hidden"},
       {"name":"kept","path":"dir/.git","kind":"directory"},
       {"name":42,"path":false},
       {"name":"absent"}, null, 17
    ],"truncated":true}"#).unwrap();
    let mut loose=String::with_capacity(128);
    loose.push_str("dir/loose.rs");
    mixed["entries"][3]["path"]=Value::String(loose);
    sample("mixed",mixed);
}
