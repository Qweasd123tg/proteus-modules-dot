use desktop_tool_display_probe::tool_display::{
    PlanStep, StepStatus, UPDATE_PLAN, headline, plan_steps,
};
use serde_json::{Value, json};
use std::hint::black_box;
#[cfg(not(feature = "count"))]
use std::time::Instant;

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

// Intentional simple reference, independent of the two production versions.
fn check(args: &Value) {
    let mut expected = Vec::new();
    let mut count = 0;
    let mut first = None;
    if let Some(rows) = args.get("plan").and_then(Value::as_array) {
        for row in rows {
            if let (Some(step), Some(status)) = (row["step"].as_str(), row["status"].as_str()) {
                let status = if status == "completed" {
                    count += 1;
                    StepStatus::Completed
                } else if status == "in_progress" {
                    first.get_or_insert(step);
                    StepStatus::InProgress
                } else {
                    StepStatus::Pending
                };
                expected.push(PlanStep {
                    step: step.into(),
                    status,
                });
            }
        }
    }
    let caption = if expected.is_empty() {
        None
    } else {
        let unclipped = match first {
            None => format!("{count}/{}", expected.len()),
            Some(step) => format!("{count}/{} · {}", expected.len(), step),
        };
        Some(unclipped.chars().take(300).collect::<String>())
    };
    let actual = headline(UPDATE_PLAN, args);
    assert_eq!(actual.label, UPDATE_PLAN);
    assert_eq!(actual.subject, caption);
    assert_eq!(actual.subject_key, None);
    assert_eq!(actual.stats, None);
    assert_eq!(plan_steps(args), expected);
}

fn checks() -> usize {
    let statuses = [
        json!({}),
        json!({"status": null}),
        json!({"status":3}),
        json!({"status":"completed"}),
        json!({"status":"in_progress"}),
        json!({"status":"pending"}),
        json!({"status":"in_progress "}),
        json!({"status":""}),
    ];
    let steps = [
        json!(null),
        json!(4),
        json!(false),
        json!(""),
        json!("a"),
        json!("  All \n "),
        json!("я🦀".repeat(148)),
        json!("a\u{200d}я🦀".repeat(119)),
    ];
    let mut n = 0;
    for status in &statuses {
        for step in &steps {
            let mut entry = status.clone();
            entry["step"] = step.clone();
            for plan in [
                json!([entry]),
                json!([null, {}, entry, {"step":"later", "status":"in_progress"}]),
                json!([{"step":"first", "status":"in_progress"}, entry, entry]),
            ] {
                check(&json!({"plan":plan}));
                n += 1;
            }
        }
    }
    for args in [
        json!(null),
        json!({"plan":null}),
        json!({"plan":{}}),
        json!({"plan":[{},false]}),
    ] {
        check(&args);
        n += 1;
    }
    n
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    let data = [
        ("empty", json!({"plan":[]})),
        (
            "three-active",
            json!({"plan":[
                {"step":"Read settings", "status":"completed"},
                {"step":"Применить патч", "status":"in_progress"},
                {"step":"Test and report", "status":"pending"}
            ]}),
        ),
        (
            "three-no-active",
            json!({"plan":[
                {"step":"Read settings", "status":"completed"},
                {"step":"Применить патч", "status":"completed"},
                {"step":"Test and report", "status":"failed"}
            ]}),
        ),
        (
            "empty-active",
            json!({"plan":[
                {"step":"", "status":"in_progress"},
                {"step":"later", "status":"in_progress"}
            ]}),
        ),
        (
            "oversize-active",
            json!({"plan":[{"step":"🦀я".repeat(22_000),"status":"in_progress"}]}),
        ),
        (
            "wide-plan",
            json!({"plan":(0..1024).map(|i| json!({
            "step": format!("{i} {}", if i < 10 {"Детализировать шаг и продолжить".repeat(3)} else {"Run checks and keep the report, then finish. ".repeat(4)}),
            "status": match i {
                0..256 => "completed",
                256 => "in_progress",
                _ => "pending"
            }
        })).collect::<Vec<_>>()}),
        ),
    ];
    println!("PASS {arm} {} differential cases", checks());
    for (name, args) in &data {
        check(args);
        let call = || headline(UPDATE_PLAN, black_box(args));
        #[cfg(feature = "count")]
        {
            let (a, b) = counter::read();
            let result = call();
            let (c, d) = counter::read();
            black_box(&result);
            println!("alloc\t{arm}\t{name}\t{}\t{}", c - a, d - b);
        }
        #[cfg(not(feature = "count"))]
        {
            let n = if name.starts_with("wide") || name.starts_with("oversize") {
                16
            } else {
                256
            };
            let mut samples = Vec::new();
            for _ in 0..22 {
                let now = Instant::now();
                for _ in 0..n {
                    black_box(call());
                }
                samples.push(now.elapsed().as_nanos() / n);
            }
            samples.remove(0);
            samples.sort_unstable();
            println!("time\t{arm}\t{name}\t{}", samples[samples.len() / 2]);
        }
    }
}
