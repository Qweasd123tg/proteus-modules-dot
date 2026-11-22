// Test-only Analysis selected-task decision and disclosure meter, never installed.
use super::*;
use proteus_extension::{ValueExt, json};
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
    static SOURCE: Cell<Option<(*const u8,usize)>> = const { Cell::new(None) };
    static VISITS: Cell<usize> = const { Cell::new(0) };
    static BODY: Cell<Option<bool>> = const { Cell::new(None) };
    static DONE: Cell<Option<[usize;6]>> = const { Cell::new(None) };
}

pub fn begin(text:&str) {
    assert!(SOURCE.replace(Some((text.as_ptr(),text.len()))).is_none());
    assert!(METER.replace(Some((0,0))).is_none());
    VISITS.set(0);
    BODY.set(None);
}

pub fn visit() { VISITS.set(VISITS.get()+1); }

pub fn body(body:&Value) {
    if let Some((ptr,len))=SOURCE.get() {
        let text=body.as_str().unwrap();
        assert_eq!(text.len(),len);
        assert!(BODY.replace(Some(text.as_ptr()==ptr)).is_none());
    }
}

pub fn end() {
    let (calls,bytes)=METER.take().unwrap();
    let (_,len)=SOURCE.take().unwrap();
    let is_borrow=BODY.take();
    let raw_reads=[len,VISITS.get(),usize::from(is_borrow.is_some()),usize::from(is_borrow==Some(true)),calls,bytes];
    assert!(DONE.replace(Some(raw_reads)).is_none());
}

fn ordinary() -> String {
    (0..42).map(|i|format!("Проверка {i:02}: «Сводка» — preserve \"quotes\", tab\tand UTF-8 🦀 in the update.\r\n")).collect()
}

#[test]
fn measure_selected_task_projection() {
    fn sample(name:&str,input:Value) {
        let expected=input.as_str().unwrap_or_default();
        let raw_chars=expected.chars().count();
        let turn=json!({"turn_id":"probe","task":{"text":&input},
                       "config_snapshot":{"fixture":true},"output":{"text":"control"}});
        let root=crate::summary::turn_summary(&turn,&Value::Null,&Value::Null,&crate::nodes::Open);
        let [bytes,visits,shown,original,calls,requested]=DONE.take().unwrap();
        assert_eq!(bytes,expected.len());
        assert_eq!(shown,usize::from(raw_chars>600));
        let mut capacity=0;
        if let Some(task)=root.list("children").iter().find(|v|v.str("id")=="turn:probe:task") {
            assert_eq!(task["open"],false);
            let Value::String(text)=&task["children"][0]["text"] else { panic!("missing text") };
            assert_eq!(text,expected);
            capacity=text.capacity();
        } else {
            assert_eq!(shown,0);
        }
        println!("\nops {name} {bytes} {raw_chars} {visits} {shown} {original} {capacity} {calls} {requested}");
        println!("tree {name} {root}");
    }

    sample("empty",json!(""));
    sample("malformed",json!([2,"fake"]));
    sample("short",json!("🦀".repeat(599)));
    sample("exact",json!("🦀".repeat(600)));
    sample("just-over",json!("е\u{301}".repeat(300)+"\r"));
    sample("whitespace",json!("\u{2003}".repeat(601)));
    let s=ordinary();
    assert!((2048..=8192).contains(&s.len()));
    sample("ordinary",json!(s));
}
