use std::alloc::{GlobalAlloc, Layout, System};
use std::io::Write;
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

struct Counter;
static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static REALLOCS: AtomicUsize = AtomicUsize::new(0);
#[global_allocator]
static GLOBAL: Counter = Counter;
// Instrumentation only: the production System allocator performs every operation.
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Relaxed);
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Relaxed);
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, size: usize) -> *mut u8 {
        REALLOCS.fetch_add(1, Relaxed);
        unsafe { System.realloc(p, l, size) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
mod core {
    #[derive(Default)]
    pub struct TopologySnapshot {
        pub profile: String,
        pub cwd: String,
        pub module_epoch: usize,
        pub model: Option<Model>,
        pub hooks: Vec<String>,
        pub slots: Vec<Slot>,
        pub modules: Vec<Module>,
        pub tools: Vec<Tool>,
        pub warnings: Vec<Warning>,
    }
    pub struct Model {
        pub provider: String,
        pub name: String,
    }
    pub struct Slot {
        pub active_module: Option<String>,
        pub id: String,
    }
    pub struct Module {
        pub slot: String,
        pub id: String,
        pub source: String,
    }
    pub struct Tool {
        pub name: String,
        pub safety: String,
        pub source: String,
        pub enabled: bool,
        pub registered: bool,
    }
    pub struct Warning {
        pub severity: String,
        pub message: String,
    }
}
mod topology_render {
    mod helpers {
        pub(super) fn module_source_label(s: &str) -> String {
            s.into()
        }
        pub(super) fn yes_no(b: bool) -> &'static str {
            if b { "yes" } else { "no" }
        }
    }
    pub mod table {
        include!(env!("TABLE_RS"));
        pub fn rows<const N: usize>(headers: [&str; N], rows: &[[String; N]]) -> String {
            render_table(headers, rows)
        }
    }
}
use topology_render::table::{render_topology_table, rows};

fn tool_rows(n: usize) -> Vec<[String; 5]> {
    (0..n)
        .map(|i| {
            [
                format!("tool{i}"),
                "read".into(),
                "builtin".into(),
                if i % 2 == 0 {
                    "yes".into()
                } else {
                    "no".into()
                },
                "yes".into(),
            ]
        })
        .collect()
}
fn snapshot(n: usize) -> core::TopologySnapshot {
    core::TopologySnapshot {
        profile: "dev".into(),
        cwd: "/work/project".into(),
        module_epoch: 1,
        model: Some(core::Model {
            provider: "example".into(),
            name: "sample".into(),
        }),
        hooks: vec!["one".into(), "two".into()],
        slots: vec![
            core::Slot {
                id: "slot-a".into(),
                active_module: Some("sample".into()),
            },
            core::Slot {
                id: "slot-b".into(),
                active_module: None,
            },
        ],
        modules: vec![core::Module {
            slot: "slot-a".into(),
            id: "sample".into(),
            source: "builtin".into(),
        }],
        tools: (0..n)
            .map(|i| core::Tool {
                name: format!("tool{i}"),
                safety: "read".into(),
                source: "builtin".into(),
                enabled: i % 2 == 0,
                registered: true,
            })
            .collect(),
        warnings: vec![core::Warning {
            severity: "info".into(),
            message: "sample".into(),
        }],
    }
}
fn measure(label: &str, n: usize, f: impl FnOnce() -> String) {
    let (a, b) = (ALLOCS.load(Relaxed), REALLOCS.load(Relaxed));
    let result = std::hint::black_box(f());
    let (c, d) = (ALLOCS.load(Relaxed), REALLOCS.load(Relaxed));
    println!("{label} {n} {} {} {}", result.len(), c - a, d - b);
}
fn main() {
    let headers = ["tool", "safety", "source", "enabled", "registered"];
    if std::env::args().nth(1).as_deref() == Some("measure") {
        for n in [0, 1, 4, 16, 64, 256, 1000] {
            let list = tool_rows(n);
            let snap = snapshot(n);
            measure("table", n, || rows(headers, std::hint::black_box(&list)));
            measure("whole", n, || {
                render_topology_table(std::hint::black_box(&snap))
            });
        }
        return;
    }
    let mut output = std::io::stdout().lock();
    let mut emit = |s: String| {
        output.write_all(&(s.len() as u64).to_le_bytes()).unwrap();
        output.write_all(s.as_bytes()).unwrap();
    };
    let sample = rows(
        ["A", "B"],
        &[["é".into(), "abc".into()], ["xx".into(), "".into()]],
    );
    assert_eq!(sample, "A   B  \n--  ---\né   abc\nxx     ");
    emit(sample);
    emit(rows::<0>([], &[[], []]));
    let vals = [
        "",
        "ascii",
        "two words",
        "é",
        "e\u{301}",
        "界",
        "⌘",
        "a\nb",
        " x ",
        "abc\t",
    ];
    for a in 0..vals.len() {
        for b in 0..vals.len() {
            for c in 0..vals.len() {
                emit(rows(
                    [vals[a], vals[b], vals[c]],
                    &[
                        [vals[b].into(), vals[c].into(), vals[a].into()],
                        [vals[c].into(), vals[a].into(), vals[b].into()],
                    ],
                ));
            }
        }
    }
    for n in [0, 1, 4, 16, 64, 256, 1000] {
        emit(rows(headers, &tool_rows(n)));
        emit(render_topology_table(&snapshot(n)));
    }
}
