// Test-only instruction-line and step-card allocation counters; never part of the product patch.
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

fn scope<T>(op: impl FnOnce() -> T) -> (T, usize, usize) {
    assert!(METER.replace(Some((0, 0))).is_none());
    let out = std::hint::black_box(op());
    let (calls, bytes) = METER.take().unwrap();
    (out, calls, bytes)
}

fn ordinary(sizes: &[usize]) -> Vec<Value> {
    let kinds = ["System", "Developer", "Project"];
    sizes
        .iter()
        .copied()
        .enumerate()
        .map(|(i, size)| {
            let unit = format!(
                "Synthetic block {i} repeats ordinary display text, without execution. Ж🦀\r\n"
            );
            let body = unit.repeat(size / unit.len()) + &"x".repeat(size % unit.len());
            assert_eq!(body.len(), size);
            json!({"kind":kinds[i],"priority":i,"text":body})
        })
        .collect()
}

fn malformed() -> Vec<Value> {
    vec![
        json!({"kind":{"user":{}},"priority":false}),
        json!({"kind":"system","text":null}),
        json!({"kind":"developer","priority":1,"text":""}),
        json!({"kind":"context","priority":2,"text":true}),
        json!({"kind":null,"priority":3,"text":-2.75}),
        json!({"kind":"system","priority":4,"text":{"b":[true,null],"a":"Ж"}}),
        json!({"kind":"context","priority":{"note":1},"text":[1,false]}),
        json!(42),
    ]
}

fn amounts(blocks: &[Value]) -> (usize, usize) {
    blocks
        .iter()
        .filter_map(|block| block.opt_str("text"))
        .filter(|text| !text.is_empty())
        .fold((0, 0), |(n, b), text| (n + 1, b + text.len()))
}

fn original_line(block: &Value) -> String {
    let kind = text::tagged(block.at("kind"));
    format!(
        "[{kind} · приоритет {}]\n{}",
        plain(block.at("priority")),
        get(block, "text", "")
    )
}

fn lines(case: &str, blocks: &[Value]) {
    let mut output = Vec::with_capacity(blocks.len());
    let ((), calls, bytes) = scope(|| {
        for row in blocks {
            output.push(format_instruction(std::hint::black_box(row)));
        }
    });
    assert_eq!(
        output,
        blocks.iter().map(original_line).collect::<Vec<_>>(),
        "{case}"
    );
    let len: usize = output.iter().map(String::len).sum();
    let cap: usize = output.iter().map(String::capacity).sum();
    let (eligible, payload) = amounts(blocks);
    println!(
        "\nops {case} {} {eligible} {payload} {len} {cap} {calls} {bytes}",
        blocks.len()
    );
    println!("tree {case} {}", json!(output));
}

fn find<'a>(node: &'a Value, id: &str) -> Option<&'a Value> {
    if node.str("id") == id {
        return Some(node);
    }
    node.list("children").iter().find_map(|node| find(node, id))
}

fn card(case: &str, blocks: &[Value]) {
    let step = json!({"sequence":1,"started_at_ms":1000,"finished_at_ms":1520,
    "execution_id":"fixture-run","thread_id":null,"data":{
        "kind":"model","exchange_id":"model-1","origin":"direct",
        "request":{"model":{"provider":"fixture","model":"fixed"},
            "instructions":blocks,"messages":[],"tools":[]},
        "response":{"messages":[],"finish_reason":"Stop","end_turn":true,"usage":{"input_tokens":80}}
    }});
    let expected = blocks
        .iter()
        .map(original_line)
        .collect::<Vec<_>>()
        .join("\n\n");
    let (root, calls, bytes) = scope(|| step_card(std::hint::black_box(&step), &Open));
    let header = find(&root, "1:instructions").unwrap();
    assert!(!header.bool("open"));
    let code = find(header, "analysis-1:instructions").unwrap();
    let Value::String(body) = &code["text"] else {
        panic!("expected a text disclosure")
    };
    assert_eq!(
        body,
        if expected.is_empty() {
            "—"
        } else {
            &expected
        }
    );
    assert_eq!(code["language"], "text");
    assert_eq!(code["wrap"], true);
    let (eligible, payload) = amounts(blocks);
    println!(
        "\nops {case} {} {eligible} {payload} {} {} {calls} {bytes}",
        blocks.len(),
        body.len(),
        body.capacity()
    );
    println!("tree {case} {}", serde_json::to_string(&root).unwrap());
}

#[test]
fn measure_instruction_text() {
    let one = ordinary(&[4096]);
    let three = ordinary(&[3072, 4096, 4608]);
    let odd = malformed();
    let empty = [json!({"kind":"system","priority":0,"text":""})];
    let _ = format_instruction(&one[0]);
    lines("line-empty-list", &[]);
    lines("line-empty-text", &empty);
    lines("line-mixed-malformed", &odd);
    lines("line-one", &one);
    lines("line-three", &three);
    card("card-empty-list", &[]);
    card("card-empty-text", &empty);
    card("card-mixed-malformed", &odd);
    card("card-one", &one);
    card("card-three", &three);
}
