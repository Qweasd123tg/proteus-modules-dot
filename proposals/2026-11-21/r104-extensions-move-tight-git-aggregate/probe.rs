// Test-only instrumentation of the actual combined Git patch widget projection.
use super::*;
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

pub struct Input {
    len: usize,
    cap: usize,
    ptr: *const u8,
}

thread_local! {
    static DONE: Cell<Option<[usize;6]>> = const { Cell::new(None) };
}

pub fn begin(patch: &String) -> Input {
    assert!(METER.replace(Some((0,0))).is_none());
    Input {len:patch.len(),cap:patch.capacity(),ptr:patch.as_ptr()}
}

pub fn end(input: Input, node: &Value) {
    let (calls,bytes)=METER.take().unwrap();
    let Value::String(result)=&node["patch"] else { panic!("patch is not a string") };
    assert_eq!((result.len(),result.capacity()),(input.len,input.len));
    let moved=usize::from(input.len>0 && result.as_ptr()==input.ptr);
    assert!(DONE.replace(Some([input.len,input.cap,result.capacity(),moved,calls,bytes])).is_none());
}

fn patch(n:usize) -> String {
    let mut s=format!("diff --git a/notes.txt b/notes.txt\n--- a/notes.txt\n+++ b/notes.txt\n@@ -0,0 +1,{n} @@\n");
    for i in 0..n {
        s.push_str(&format!("+Line {i:03}: retention check, \"quoted\" note, data and UTF-8 Ж.\n"));
    }
    s
}

#[test]
fn measure_aggregate_widget_projection() {
    fn sample(name:&str, patches:&[Option<&str>], expected:&str) {
        let mut git=Git::default();
        let entries=patches.iter().enumerate().map(|(i,s)| {
            let path=format!("synthetic-{i}.txt");
            let mut result=json!({"path":path,"kind":if s.is_none() {"binary"} else {"text"},"revision":"r"});
            if let Some(patch)=s {result["patch"]=json!(patch);}
            git.diffs.insert(path.clone(), result.into());
            json!({"path":path,"status":"modified","revision":"r"})
        }).collect::<Vec<_>>();
        git.changes=std::rc::Rc::new(json!({"entries":entries}));
        let host=Host::default();
        if name=="ordinary-repeat" {
            let _ = git.changes_document(&host).unwrap();
            let _ = DONE.take().unwrap();
        }
        let body=git.changes_document(&host).unwrap();
        let node=body.last().unwrap();
        assert_eq!(node["patch"].as_str(),Some(expected));
        let [len,input_cap,out_cap,moved,allocs,bytes]=DONE.take().unwrap();
        println!("\nops {name} {len} {input_cap} {out_cap} {moved} {allocs} {bytes}");
        println!("tree {name} {node}");
    }
    sample("empty",&[None],"");
    sample("short-lf",&[Some("+x\n")],"+x\n");
    let ordinary=patch(96);
    assert!((2048..=12288).contains(&ordinary.len()));
    sample("ordinary",&[Some(&ordinary)],&ordinary);
    sample("ordinary-repeat",&[Some(&ordinary)],&ordinary);
    let pair=[Some(ordinary.as_str()),Some(ordinary.as_str())];
    sample("two-equal",&pair,&ordinary.repeat(2));
    let small=patch(40);
    let loose=small.trim_end_matches('\n');
    sample("mixed-spare",&[None,Some(loose),Some("+Ж \"q\"\t\r\n")],&format!("{small}+Ж \"q\"\t\r\n"));
    sample("empty-string",&[Some("")],"\n");
}
