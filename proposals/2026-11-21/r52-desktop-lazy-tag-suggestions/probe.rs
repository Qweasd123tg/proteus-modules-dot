mod candidate;
mod stock;

use proteus_contracts::app_protocol::config_builder::*;
use proteus_contracts::domain::{ConfigField, ConfigValueSchema};
use serde_json::{Value, json};
use std::hint::black_box;

#[cfg(feature = "count")]
mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
    struct Counter;
    static CALLS: AtomicUsize = AtomicUsize::new(0);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    #[global_allocator]
    static A: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(layout.size(), Relaxed);
            unsafe { System.alloc(layout) }
        }
        unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
            unsafe { System.dealloc(p, layout) }
        }
        unsafe fn realloc(&self, p: *mut u8, layout: Layout, new: usize) -> *mut u8 {
            CALLS.fetch_add(1, Relaxed);
            BYTES.fetch_add(new, Relaxed);
            unsafe { System.realloc(p, layout, new) }
        }
    }
    pub fn read() -> (usize, usize) {
        (CALLS.load(Relaxed), BYTES.load(Relaxed))
    }
}

fn schema() -> ConfigField {
    ConfigField::new(
        "tags",
        "Tags",
        "",
        ConfigValueSchema::Array {
            items: Box::new(ConfigValueSchema::choices(&[
                ("shell", "First Ƙ"),
                ("shell", "Wrong Later Title"),
                ("case", "Μάϊος"),
                ("CASE", "Текст Я"),
                ("ος", "Ο.Σ"),
            ])),
        },
    )
    .with_default(json!(["shell", "fallback", 8, "Текст Я", "short", "same"]))
}

fn module(slot: &str, id: &str) -> ConfigBuilderModule {
    ConfigBuilderModule {
        slot: slot.into(),
        id: id.into(),
        ..Default::default()
    }
}

fn fixture(n: usize) -> ConfigBuilderSnapshot {
    let tools = [
        "shell",
        "same",
        "Patch",
        "Эхо",
        "İstanbul",
        "ΟΣ",
        "wrong-later",
    ]
    .into_iter()
    .map(str::to_owned)
    .chain((0..n).map(|i| {
        if i % 5 == 0 {
            format!("helper-{i}")
        } else {
            format!("tool-{i}")
        }
    }))
    .map(|name| ConfigBuilderTool {
        name,
        ..Default::default()
    })
    .collect();
    let exports = ["same", "before", "late", "wrong", "wrong-later"]
        .into_iter()
        .enumerate()
        .map(|(i, id)| ConfigBuilderPluginExport {
            slot: if i == 3 { "other" } else { "context" }.into(),
            id: id.into(),
            active: i % 2 == 0,
            description: None,
            config_schema: None,
        })
        .collect();
    ConfigBuilderSnapshot {
        tools,
        slots: vec![ConfigBuilderSlot {
            modules: vec![
                module("context", "same"),
                module("context", "slot"),
                module("other", "wrong"),
            ],
            ..Default::default()
        }],
        model_modules: vec![module("context", "model"), module("context", "same")],
        hook_modules: vec![module("context", "hook"), module("context", "model")],
        plugins: vec![ConfigBuilderPlugin {
            id: "fixture".into(),
            command: "not launched".into(),
            description: None,
            icon: None,
            exports,
            tool_packs: Vec::new(),
        }],
        ..Default::default()
    }
}

fn check(
    field: &ConfigField,
    snapshot: Option<&ConfigBuilderSnapshot>,
    selected: &[Value],
    query: &str,
) {
    let a = stock::visible(field, snapshot, selected, query);
    let b = candidate::visible(field, snapshot, selected, query);
    assert!(a.len() <= 8);
    assert_eq!(a.len(), b.len(), "query {query:?}");
    for ((value, title), row) in a.iter().zip(&b) {
        assert_eq!((value, title), (&row.value, &row.title), "query {query:?}");
    }
}

fn parity() {
    let field = schema();
    let string_field = ConfigField::new(
        "tags",
        "Tags",
        "",
        ConfigValueSchema::Array {
            items: Box::new(ConfigValueSchema::String {
                multiline: false,
                secret: false,
            }),
        },
    );
    let fields = [
        field.clone(),
        field.clone().suggest_tools(),
        field.clone().suggest_exports("context"),
        field.suggest_exports("other"),
        string_field.clone().suggest_tools(),
        string_field.suggest_exports("context"),
        ConfigField::new("tags", "Tags", "", ConfigValueSchema::Json {}).with_default(json!([
            "default",
            {},
            null
        ])),
    ];
    let mut count = 0;
    for n in [0, 1, 6, 24, 73, 320] {
        let mut snapshot = fixture(n);
        for i in 0..3 {
            // Exercise unmodified input order and precedence on a different order.
            if i == 1 {
                snapshot.tools.reverse();
            }
            if i == 2 {
                snapshot.tools.rotate_left(2);
            }
            for field in &fields {
                for input in [None, Some(&snapshot)] {
                    for selected in [
                        json!([]),
                        json!(["shell", "fallback", 2]),
                        json!(["shell", "shell", "late", {}, null]),
                        json!(["tool-1", "helper-0", "CASE", false]),
                    ] {
                        for word in [
                            "",
                            " ",
                            "fallback",
                            "later",
                            "LATER",
                            "wrong",
                            "FIRST",
                            "мАй",
                            "ТЕКСТ",
                            "ΟΣ",
                            "İST",
                            "same",
                            "before",
                            "tool-1",
                            "helper",
                            "AbsENT",
                        ] {
                            check(field, input, selected.as_array().unwrap(), word);
                            count += 1;
                        }
                    }
                }
            }
        }
    }
    println!("PASS {count} ordered full-row comparisons");
}

fn measure<T>(call: impl Fn() -> T, arm: &str, name: &str, _iterations: usize) {
    #[cfg(feature = "count")]
    {
        let (a, b) = counter::read();
        let result = black_box(call());
        let (c, d) = counter::read();
        black_box(&result);
        println!("alloc\t{arm}\t{name}\t{}\t{}", c - a, d - b);
    }
    #[cfg(not(feature = "count"))]
    {
        for _ in 0..32 {
            drop(black_box(call()));
        }
        let started = std::time::Instant::now();
        for _ in 0.._iterations {
            drop(black_box(call()));
        }
        let ns = started.elapsed().as_nanos() as f64 / _iterations as f64;
        println!("time\t{arm}\t{name}\t{ns:.3}");
    }
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
        return;
    }
    let field = schema().suggest_tools();
    let s = fixture(17);
    let m = fixture(73);
    let l = fixture(505);
    let selected = [json!("shell"), json!("fallback"), json!("helper-0")];
    for (name, snapshot, query, n) in [
        ("24-open", &s, "", 20000),
        ("24-type", &s, "helper", 10000),
        ("80-miss", &m, "not-in-registry", 3000),
        ("512-open", &l, "", 250),
    ] {
        let call_input = || {
            (
                black_box(&field),
                black_box(Some(snapshot)),
                black_box(&selected[..]),
                black_box(query),
            )
        };
        match arm.as_str() {
            "stock" => measure(
                || {
                    let (a, b, c, d) = call_input();
                    stock::visible(a, b, c, d)
                },
                &arm,
                name,
                n,
            ),
            "candidate" => measure(
                || {
                    let (a, b, c, d) = call_input();
                    candidate::visible(a, b, c, d)
                },
                &arm,
                name,
                n,
            ),
            _ => panic!("expected parity, stock or candidate"),
        }
    }
}
