// Exercise the normal formatter against its exact old body, in one Core test.
use super::*;
use crate::r58_alloc::measure;

fn map(rows: impl IntoIterator<Item = (String, Vec<String>)>) -> HashMap<String, UserInputAnswer> {
    rows.into_iter()
        .map(|(k, v)| (k, UserInputAnswer::new(v)))
        .collect()
}

fn small<const N: usize>(rows: [(&str, &[&str]); N]) -> HashMap<String, UserInputAnswer> {
    map(rows
        .into_iter()
        .map(|(k, v)| (k.into(), v.iter().map(|s| (*s).into()).collect())))
}

#[test]
fn r58_paired_answer_formatter_preserves_bytes_and_sizing() {
    let mut output = vec![];
    let long = "🧪\0Привет\r\n".repeat(5_000);
    for (case, args) in [
        ("no_answers", small([])),
        ("one_choice", small([("Language", &["Rust"])])),
        ("none_selected", small([("Language", &[])])),
        ("empty_choices", small([("", &["", ""])])),
        (
            "three_typical",
            small([
                ("stage", &["Experimental"]),
                ("language", &["Rust", "TypeScript"]),
                ("mode", &["Preset A", "Local", "Remote", "Manual"]),
            ]),
        ),
        (
            "unicode_multiline",
            small([
                ("яблоко", &["  À,œ\r\n", "\0字🌍 "]),
                ("A\nquestion", &["", "B: C\n", "\r"]),
                (" Alpha", &["?", "a\t", ", "]),
            ]),
        ),
        ("long_response", map([(String::from("note"), vec![long])])),
        (
            "larger_map_stress",
            map((0..64).rev().map(|n| {
                (
                    format!("item{n:02}"),
                    vec![format!("val{n:02} 📃"), "last  ".into()],
                )
            })),
        ),
    ] {
        let (stock, a) = measure(|| stock_format_user_input_response(&args));
        let (candidate, b) = measure(|| format_user_input_response(&args));
        assert_eq!(candidate.as_bytes(), stock.as_bytes(), "{case}");
        assert_eq!(
            candidate.capacity(),
            candidate.len(),
            "{case}: retained capacity"
        );
        assert!(candidate.capacity() <= stock.capacity());
        if !args.is_empty() {
            assert!(b.calls < a.calls && b.bytes < a.bytes, "{case}");
        } else {
            assert_eq!((b.calls, b.bytes), (a.calls, a.bytes), "{case}");
        }
        println!(
            "r58 {case}: calls {}->{}, bytes {}->{}, output {}",
            a.calls,
            b.calls,
            a.bytes,
            b.bytes,
            candidate.len()
        );
        output.push(json!([case, candidate]));
    }

    let fragments = ["", "a", "\n", "🌍 ", " ,", "a\0\r\n"];
    let keys = ["z", "α", "a", "\n", " ", ""];
    for (k1, key1) in keys.iter().enumerate() {
        for (k2, key2) in keys.iter().enumerate() {
            if k1 == k2 {
                continue;
            }
            for first in fragments {
                for second in fragments {
                    let args = small([(*key1, &[first, "", second]), (*key2, &[second])]);
                    let candidate = format_user_input_response(&args);
                    assert_eq!(
                        candidate.as_bytes(),
                        stock_format_user_input_response(&args).as_bytes()
                    );
                    assert_eq!(candidate.capacity(), candidate.len());
                    output.push(json!(candidate));
                }
            }
        }
    }
    assert_eq!(output.len(), 1088);
    let path = std::env::var("R58_ANSWER_SNAPSHOT").unwrap();
    std::fs::write(path, serde_json::to_vec(&output).unwrap()).unwrap();
}
