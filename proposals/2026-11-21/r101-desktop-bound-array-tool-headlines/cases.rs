use crate::{AppApprovalRequest, Call, Preview, approval_body, count, tool_display};
use serde_json::{Value, json};
use std::io::{BufWriter, Write};

struct Trace {
    file: BufWriter<std::fs::File>,
    records: usize,
}

impl Trace {
    fn record(&mut self, b: &[u8]) {
        self.file.write_all(b).unwrap();
        self.file.write_all(b"\n").unwrap();
        self.records += 1;
    }
}

type Observation = (Option<String>, Option<String>);

fn snapshot(name: &str, args: &Value, digest: &mut Trace) -> Observation {
    let h = tool_display::headline(name, args);
    let key = h.subject_key.as_deref();
    let details = tool_display::other_args(args, key);
    let paths = tool_display::path_list_preview(&h, args);
    let mut request = AppApprovalRequest {
        call: Call {
            name: name.into(),
            args: args.clone(),
        },
        preview: None,
    };
    let fallback = approval_body(&request);
    request.preview = Some(Preview {
        body: Some("Synthetic server preview\n\r🦀".into()),
    });
    let present = approval_body(&request);
    assert_eq!(present.as_deref(), Some("Synthetic server preview\n\r🦀"));
    request.preview = Some(Preview { body: None });
    assert_eq!(approval_body(&request), None);
    let observation = json!([
        name, h.label, h.subject, h.stats, key, paths, details, fallback, present
    ]);
    digest.record(&serde_json::to_vec(&observation).unwrap());
    (h.subject, h.subject_key)
}

// Independent uncapped historical rule, deliberately retaining the temporary
// array/format work so the test does not recite the candidate algorithm.
fn legacy(key: &str, values: &[Value]) -> Option<String> {
    let parts = values.iter().filter_map(Value::as_str).collect::<Vec<_>>();
    let old = match parts.as_slice() {
        [] => return None,
        [only] => only
            .lines()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" ↵ "),
        [first, rest @ ..] if key.ends_with('s') => format!("{first} +{}", rest.len()),
        _ => parts.join(" "),
    };
    (!old.is_empty()).then(|| old.chars().take(300).collect())
}

fn shaped(n: usize) -> Value {
    let mut paths = vec![
        "desktop/tests/configuration/focused/файл-🦀.rs".to_owned(),
        "desktop/tests/synthetic-with-quote\"/render\npreview.rs".to_owned(),
    ];
    paths.extend((2..n).map(|k| format!("desktop/tests/focused/fixtures/subfolder/item-{k}.rs")));
    json!({"paths": paths, "zeta": "preserved", "line_numbers": true, "max_bytes_total": 32768, "max_output_tokens": 64, "alpha": "first", "note": null})
}

fn check_array(name: &str, key: &str, values: Vec<Value>, digest: &mut Trace) {
    let expect = legacy(key, &values);
    let args = json!({key: values, "z_payload": "dot", "a_payload": 12, "note": null});
    let (subject, selected) = snapshot(name, &args, digest);
    assert_eq!(selected.as_deref(), expect.as_ref().map(|_| key));
    assert_eq!(subject, expect);
}

#[test]
fn selected_display_paths_and_actual_approval_body_are_unchanged() {
    eprintln!("ARM {}", env!("R101_ARRAY_ARM"));
    let mut digest = Trace {
        file: BufWriter::new(
            std::fs::File::create(std::env::var_os("R101_TRACE_PATH").unwrap()).unwrap(),
        ),
        records: 0,
    };
    for n in [2, 8, 20] {
        let args = shaped(n);
        assert_eq!(
            snapshot("read_many_files", &args, &mut digest).0,
            legacy("paths", args["paths"].as_array().unwrap())
        );
        let h = tool_display::headline("read_many_files", &args);
        let preview = tool_display::path_list_preview(&h, &args).unwrap();
        assert_eq!(preview.lines().count(), n);
        assert!(preview.contains("render\\npreview.rs") && preview.contains("quote\\\""));
    }

    for (first, whole) in [
        (json!(["", ""]), true),
        (json!([false, null]), false),
        (json!(["  "]), false),
    ] {
        let args =
            json!({"cmd":first, "command":"synthetic file read", "justification":"do not display"});
        let req = AppApprovalRequest {
            call: Call {
                name: "custom".into(),
                args,
            },
            preview: None,
        };
        let actual = approval_body(&req).unwrap();
        if whole {
            assert_eq!(
                serde_json::from_str::<Value>(&actual).unwrap(),
                json!({"cmd":["",""], "command":"synthetic file read"})
            );
        } else {
            assert_eq!(actual, "synthetic file read");
        }
        digest.record(&serde_json::to_vec(&actual).unwrap());
    }
    let number = json!(1.25e-30);
    let empty = [
        "",
        "    ",
        "\u{2002}\t",
        "a\rb\r\nc",
        "e\u{0301}👩\u{200d}🚀\u{202e}",
        "末尾",
    ];
    for (name, key) in [
        ("read_many_files", "paths"),
        ("write_stdin", "chars"),
        ("custom", "query"),
    ] {
        for first in empty {
            for second in empty {
                for values in [
                    vec![],
                    vec![json!(false), Value::Null],
                    vec![Value::Null, json!(first), number.clone()],
                    vec![json!(first), Value::Null, json!(second)],
                    vec![
                        json!(first),
                        json!(second),
                        json!(first),
                        json!({"n":2}),
                        json!(second),
                    ],
                ] {
                    // The candidate cannot select the fallback z_payload
                    // here because numeric/array cases remain covered below.
                    if name == "custom" && legacy(key, &values).is_none() {
                        let args = json!({key:values, "z_payload": 11});
                        assert_eq!(snapshot(name, &args, &mut digest), (None, None));
                    } else {
                        check_array(name, key, values, &mut digest);
                    }
                }
            }
        }
        for n in [0, 1, 2, 150, 296, 297, 298, 299, 300, 301, 302] {
            for unit in ["a", "я", "🚀", "\u{0301}", "\u{202e}"] {
                for others in [1usize, 2, 9, 10, 19, 20, 99, 100, 101] {
                    let mut parts = vec![json!(unit.repeat(n)), json!(false)];
                    for j in 0..others {
                        parts.extend([
                            json!(if j % 2 == 0 { "" } else { "я🚀\r\n  next" }),
                            Value::Null,
                        ]);
                    }
                    check_array(name, key, parts, &mut digest);
                }
            }
        }
    }

    let args = json!({"cmd":[1, null], "path":["  ", false], "query":["", ""], "url":"alternate"});
    assert_eq!(
        snapshot("custom", &args, &mut digest),
        (Some(" ".into()), Some("query".into()))
    );
    let args =
        serde_json::from_str(r#"{"z_caption":"first inserted","a_caption":"lexical first"}"#)
            .unwrap();
    let expected = if cfg!(feature = "preserve_order") {
        "z_caption"
    } else {
        "a_caption"
    };
    assert_eq!(
        snapshot("custom", &args, &mut digest).1.as_deref(),
        Some(expected)
    );
    assert_eq!(snapshot("exec_command", &args, &mut digest), (None, None));

    for (name, args) in [
        ("custom", json!({"query": -0.0, "url":"unused"})),
        (
            "custom",
            json!({"query": 4.2e40, "detail": {"q": "payload"}}),
        ),
        (
            "custom",
            json!({"query": true, "url":"https://example.invalid/fixture"}),
        ),
        ("custom", json!("not-an-object")),
        (
            "write_stdin",
            json!({"chars":["x","y","z"], "id":"synthetic"}),
        ),
        (
            "request_permissions",
            json!({"justification":"synthetic reason", "sample":{"z":1,"a":2}}),
        ),
        (
            "update_plan",
            json!({"plan":[{"step":"review fixture","status":"in_progress"},{"step":"read","status":"completed"}]}),
        ),
        (
            "apply_patch",
            json!({"patch":"*** Begin Patch\n*** Add File: a.txt\n+hello\n*** End Patch"}),
        ),
        (
            "read_many_files",
            json!({"paths":["one.rs", 2], "zeta":true}),
        ),
    ] {
        snapshot(name, &args, &mut digest);
    }
    digest.file.flush().unwrap();
    eprintln!("TRACE complete-observations {}", digest.records);
    eprintln!("TRACE generic-first {expected}");
}

fn work(label: &str, name: &str, args: Value) {
    count::start();
    let h = std::hint::black_box(tool_display::headline(
        std::hint::black_box(name),
        std::hint::black_box(&args),
    ));
    let work = count::stop();
    assert!(h.subject.is_some());
    eprintln!("WORK {label}: {} {}", work.requests, work.bytes);
}

#[test]
fn allocates_only_for_the_visible_caption_where_possible() {
    for n in [2usize, 8, 20] {
        work(&format!("ordinary-{n}"), "read_many_files", shaped(n));
    }
    work(
        "ordinary-custom-join",
        "custom",
        json!({"query":["letter","details","notes","outline","preview"]}),
    );
    work(
        "unicode-plural-bound",
        "read_many_files",
        json!({"paths":std::iter::once("я🚀".repeat(151)).chain((0..19).map(|i|format!("src/fixture-{i}.rs"))).collect::<Vec<_>>()}),
    );
    work(
        "hidden-joined-tail",
        "custom",
        json!({"query":["α".repeat(150),"l".repeat(100),"🚀".repeat(16_384),"д".repeat(16_384)]}),
    );
    work(
        "single-nonarray-control",
        "exec_command",
        json!({"cmd":"read fixture\nread second"}),
    );
}
