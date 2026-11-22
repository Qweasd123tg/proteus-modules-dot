// Test-only Markdown scopes; never part of the product patch.
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

fn scope<T>(op: impl FnOnce() -> T) -> (T, usize, usize) {
    assert!(METER.replace(Some((0, 0))).is_none());
    let out = std::hint::black_box(op());
    let (calls, bytes) = METER.take().unwrap();
    (out, calls, bytes)
}

const SIMPLE: &str = "w_{1}=\\alpha^2+4β";
const SPECIAL: &str = "x<y &amp; z>β+é";
const FORMULAS: &[&str] = &[
    "u_1=α+β",
    "R_{ij}=x_i+y_j",
    SPECIAL,
    "s_n=\\frac{n(n+1)}{2}",
    "t=λ+2é",
    "P(X>c)=p",
    "x_{1}<x_{2}",
    "v=δ^2",
    "A_{ij}=a_i+b_j",
    "r=\\sqrt{x^2+y^2}",
    "Q=θ+ϕ",
    "p=ρ & z=η",
];

fn math_note(formulas: &[&str]) -> String {
    formulas
        .iter()
        .enumerate()
        .map(|(i, body)| {
            format!("The calculation below uses synthetic coefficients only. Term {} is ${body}$; this is its documented value.", i + 1)
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn expected_text(raw: &str) -> String {
    raw.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn sample_wrapper(name: &str, bodies: &[&str]) {
    let raw: Vec<_> = bodies.iter().map(|body| format!("${body}$")).collect();
    let slots: Vec<_> = (0..bodies.len()).map(|i| format!("inline-{i}")).collect();
    let mut output = Vec::with_capacity(bodies.len());
    let ((), calls, bytes) = scope(|| {
        for (slot, body) in slots.iter().zip(&raw) {
            output.push(format_unchanged(
                std::hint::black_box(slot),
                std::hint::black_box(body),
            ));
        }
    });
    let mut caps = 0;
    let mut lens = 0;
    for ((slot, body), fallback) in slots.iter().zip(&raw).zip(&output) {
        let wanted = format!(
            "<span data-content=\"{slot}\">{}</span>",
            expected_text(body)
        );
        assert_eq!(fallback, &wanted, "{name}");
        caps += fallback.capacity();
        lens += fallback.len();
    }
    let raw_bytes = raw.iter().map(String::len).sum::<usize>();
    println!(
        "\nops {name} {raw_bytes} {} {lens} {caps} {calls} {bytes}",
        bodies.len()
    );
    println!("tree {name} {}", serde_json::to_string(&output).unwrap());
}

fn sample_render(name: &str, source: &str, languages: &[String], count: usize) {
    let (root, calls, bytes) =
        scope(|| render("fixture", std::hint::black_box(source), languages).unwrap());
    let actual = root["inlines"].as_array().map(Vec::len).unwrap_or_default();
    assert_eq!(actual, count, "{name}");
    let Value::String(html) = &root["html"] else {
        panic!("expected HTML");
    };
    println!(
        "\nops {name} {} {actual} {} {} {calls} {bytes}",
        source.len(),
        html.len(),
        html.capacity()
    );
    println!("tree {name} {}", serde_json::to_string(&root).unwrap());
}

#[test]
fn measure_inline_fallback() {
    let language = ["latex".into()];
    let dense = format!("λ{}β", "<>&".repeat(512));
    // Initialize both scopes before collecting the first sample.
    let _ = render("fixture", "$x$", &language).unwrap();
    let _ = format_unchanged("inline-0", "$x$");
    sample_wrapper("wrap-one", &[SIMPLE]);
    sample_wrapper("wrap-special", &[SPECIAL]);
    sample_wrapper("wrap-note", FORMULAS);
    sample_wrapper("wrap-dense", &[&dense]);
    sample_render(
        "render-nomath",
        "Plain **prose** with a figure of $100.",
        &language,
        0,
    );
    sample_render("render-disabled", &math_note(FORMULAS), &[], 0);
    sample_render("render-one", &math_note(&[SIMPLE]), &language, 1);
    sample_render("render-special", &math_note(&[SPECIAL]), &language, 1);
    sample_render("render-note", &math_note(FORMULAS), &language, 12);
    sample_render("render-dense", &format!("${dense}$"), &language, 1);
}
