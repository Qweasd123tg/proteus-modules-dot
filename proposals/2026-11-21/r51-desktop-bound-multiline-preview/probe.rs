use desktop_tool_display_probe::tool_display::{Headline, headline, other_args};
use serde_json::json;
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

// Reference is the old normalize-all behavior, independent from the clipping
// implementation. Shell commands are fixture text only.
fn normalized(text: &str, max: usize) -> Option<String> {
    let value = text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join(" ↵ ");
    (!value.is_empty()).then(|| value.chars().take(max).collect())
}

fn expected(name: &str, key: &str, subject: Option<String>) -> Headline {
    Headline {
        label: name.into(),
        subject_key: subject.as_ref().map(|_| key.to_owned()),
        subject,
        stats: None,
    }
}

fn check(text: &str) {
    let caption = normalized(text, 300);
    let args = json!({"cmd": text, "annotation": "f"});
    assert_eq!(
        headline("exec_command", &args),
        expected("exec_command", "cmd", caption.clone())
    );
    let generic = if caption.is_some() {
        expected("third_party", "cmd", caption.clone())
    } else {
        expected("third_party", "annotation", Some("f".to_owned()))
    };
    assert_eq!(headline("third_party", &args), generic);
    let single = json!({"paths": [null, text, 42]});
    assert_eq!(
        headline("read_many_files", &single),
        expected("read_many_files", "paths", caption)
    );
    let expanded = json!({
        "cmd": false, "note": text, "nil": null, "yield_time_ms": 30,
        "max_output_tokens": 200, "object": {"extra": 1}
    });
    assert_eq!(
        other_args(&expanded, Some("cmd")),
        [
            ("note".into(), normalized(text, 160).unwrap_or_default()),
            ("object".into(), "{1}".into()),
        ]
    );
}

fn parity() {
    let mut n = 0;
    let lines = [
        "",
        "  ",
        "abc",
        "   \t 🦀 ",
        "\u{2002}я\t",
        "\u{200b}",
        "\0",
        "e\u{301}",
        "a\rb",
        "\u{202e}abc\u{2069}",
    ];
    for a in lines {
        for b in lines {
            for c in lines {
                let input = format!("{a}\r\n{b}\n{c}");
                check(&input);
                n += 1;
            }
        }
    }
    for limit in [160, 300] {
        for count in limit - 6..=limit + 6 {
            for ch in ["x", "я", "↵", "🦀"] {
                for suffix in ["", "\r\n", "\r\n\n  \t", "\n🦀 tail", "\n \r\n  x  \r\ny"] {
                    let input = format!("   {}\t{suffix}", ch.repeat(count));
                    check(&input);
                    n += 1;
                }
            }
        }
    }
    for text in [
        "𝄞".repeat(28000),
        "one\ntwo\n".repeat(10000),
        "\r\n   ".repeat(10000),
    ] {
        check(&text);
        n += 1;
    }
    for (input, wanted) in [
        (json!({"paths":[]}), None),
        (json!({"paths":[2, null]}), None),
        (json!({"paths":[" \n\t", false]}), None),
        (json!({"paths":[" \r\n", ""]}), Some(" \r\n +1")),
        (
            json!({"paths":["\t a \n b ",true," two "]}),
            Some("\t a \n b  +1"),
        ),
    ] {
        assert_eq!(
            headline("read_many_files", &input).subject.as_deref(),
            wanted
        );
    }
    println!("PASS {n} texts × 4 exact output comparisons plus 5 array fallbacks");
}

fn main() {
    let arm = std::env::args().nth(1).unwrap();
    if arm == "parity" {
        parity();
        return;
    }
    let simple = json!({"cmd":"git status --short"});
    let short_multi = json!({"cmd":"pwd\nls -la\ngit diff"});
    let medium_multi = json!({"cmd": "printf '%s\\n' 'fixture'\n".repeat(64)});
    let long_single = json!({"cmd": "я🦀".repeat(22000)});
    let long_multi = json!({"cmd": "echo 'проверка'\n   \n".repeat(6400)});
    let arg = json!({"contents": "строка текста 🦀\n".repeat(6400), "path":"sample.md"});
    for (name, args, is_arg, iterations) in [
        ("short", simple, false, 60000),
        ("three-lines", short_multi, false, 40000),
        ("64-lines", medium_multi, false, 2500),
        ("single-wide", long_single, false, 300),
        ("multiline-wide", long_multi, false, 250),
        ("expanded-note", arg, true, 250),
    ] {
        let subject = || headline("exec_command", black_box(&args));
        let expanded = || other_args(black_box(&args), Some("path"));
        fn run<T>(call: impl Fn() -> T, arm: &str, name: &str, _iterations: u32) {
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
                for _ in 0..24 {
                    drop(black_box(call()));
                }
                let now = std::time::Instant::now();
                for _ in 0.._iterations {
                    drop(black_box(call()));
                }
                let ns = now.elapsed().as_nanos() as f64 / _iterations as f64;
                println!("time\t{arm}\t{name}\t{ns:.3}");
            }
        }
        if is_arg {
            run(expanded, &arm, name, iterations);
        } else {
            run(subject, &arm, name, iterations);
        }
    }
}
