use std::cell::Cell;

#[derive(Debug, PartialEq, Eq)]
enum Projection {
    Short(String),
    Long {
        full: bool,
        preview: String,
        label: String,
        clipped: String,
    },
}

fn compare(text: &str) -> usize {
    let mut n = 0;
    for full in [[false, false], [false, true], [true, false], [true, true]] {
        let stock = stock::Fold { full };
        let candidate = candidate::Fold { full };
        for part in [0, 1, 2, usize::MAX] {
            let before = stock.block(part, text);
            let after = candidate.block(part, text);
            assert_eq!(before, after, "full={full:?}, part={part}, bytes={}", text.len());
            n += 1;
        }
    }
    n
}

fn exhaustive(s: &mut String, depth: usize) -> usize {
    let mut n = compare(s);
    if depth > 0 {
        for c in ['a', ' ', '\t', '\n', '\r', 'я', '🤖'] {
            let keep = s.len();
            s.push(c);
            n += exhaustive(s, depth - 1);
            s.truncate(keep);
        }
    }
    n
}

fn boundaries() -> usize {
    let mut n = 0;
    for sep in ["\n", "\r\n", "\r"] {
        for target in [0, 1, 11, 12, 13, 14, 399, 400, 401, 402] {
            for line in ["", "a", "я 🤖", "\t \r", "  \u{2003}   "] {
                let raw = (line.to_owned() + sep).repeat(target);
                for last in ["", "\n", "tail", "tail\r", " \r\n", "🤖\r\n"] {
                    n += compare(&(raw.clone() + last));
                }
            }
        }
    }
    for limit in [12, 400, 2_000, 40_000] {
        for size in [limit - 2, limit - 1, limit, limit + 1, limit + 2, limit + 3] {
            for unit in ["a", " ", "я", "🤖", "я\r\n🤖 ", "x\n"] {
                let text = unit.repeat(size / unit.len()) + &"a".repeat(size % unit.len());
                assert_eq!(text.len(), size);
                n += compare(&text);
            }
        }
    }
    for cap in [2_000, 40_000] {
        for missing in 1..=4 {
            let prefix = "a".repeat(cap - missing);
            n += compare(&(prefix.clone() + "🤖\r\n\nlast"));
            n += compare(&(prefix + "яя trailing\u{2003}\r\n"));
        }
    }
    let lf12 = "a".repeat(1988) + &"\n".repeat(12);
    let lf13 = "a".repeat(1987) + &"\n".repeat(12) + "x";
    let crlf12 = "a".repeat(1976) + &"\r\n".repeat(12);
    let crlf13 = "a".repeat(1975) + &"\r\n".repeat(12) + "x";
    for text in [&lf12, &lf13, &crlf12, &crlf13] {
        assert_eq!(text.len(), 2_000);
        n += compare(text);
    }
    assert_eq!(lf12.lines().count(), 12);
    assert_eq!(lf13.lines().count(), 13);
    assert_eq!(crlf12.lines().count(), 12);
    assert_eq!(crlf13.lines().count(), 13);
    n
}

fn expectations() {
    let expanded = candidate::Fold { full: [true, false] };
    let cap = "я".repeat(1_000);
    assert!(matches!(expanded.block(0, &cap), Projection::Short(s) if s == cap));
    let raw = cap + "x";
    assert!(matches!(expanded.block(0, &raw), Projection::Long { full: true, label, .. } if label == "Свернуть"));
    assert!(matches!(expanded.block(1, &raw), Projection::Long { full: false, label, .. } if label == "Показать больше"));
    assert!(matches!(expanded.block(usize::MAX, &" ".repeat(2_001)), Projection::Long { full: false, preview, label, .. } if preview.is_empty() && label == "Показать больше · ещё строк: 1"));
    let raw = "head\n".to_owned() + &" \r\n".repeat(11) + "tail";
    assert!(matches!(expanded.block(1, &raw), Projection::Long { full: false, preview, label, .. } if preview == "head" && label == "Показать больше · ещё строк: 12"));
    let raw = "a".repeat(1_999) + "🤖";
    assert!(matches!(expanded.block(1, &raw), Projection::Long { preview, .. } if preview == "a".repeat(1_999)));
    let raw = "a".repeat(39_999) + "🤖";
    assert!(matches!(expanded.block(0, &raw), Projection::Long { clipped, .. } if clipped == "a".repeat(39_999) + "\n… Текст обрезан"));
    assert!(matches!(expanded.block(0, &"x\n".repeat(401)), Projection::Long { clipped, .. } if clipped == "x\n".repeat(400) + "Ещё строк: 1"));
}

fn witness(name: &str, text: &str, full: [bool; 2], part: usize, want: [(usize, usize); 2]) {
    let a = stock::Fold { full };
    let b = candidate::Fold { full };
    let (source_lines, preview_lines) = (Cell::new(0), Cell::new(0));
    let stock = a.counted(part, text, &source_lines, &preview_lines);
    let counts_a = (source_lines.replace(0), preview_lines.replace(0));
    let candidate = b.counted(part, text, &source_lines, &preview_lines);
    let counts_b = (source_lines.get(), preview_lines.get());
    assert_eq!(stock, a.block(part, text));
    assert_eq!(candidate, b.block(part, text));
    assert_eq!(stock, candidate);
    assert_eq!([counts_a, counts_b], want, "{name}");
    println!(
        "{name}: source/preview classifier-caption yields {}/{} -> {}/{}",
        counts_a.0, counts_a.1, counts_b.0, counts_b.1,
    );
}

fn main() {
    let exhaustive = exhaustive(&mut String::new(), 5);
    let thresholds = boundaries();
    expectations();
    println!("paired projections: exhaustive={exhaustive} boundary={thresholds}");
    let many = "x\n".repeat(65_536);
    witness("full 65,536 lines", &many, [true, false], 0, [(65_536, 12), (0, 0)]);
    witness("collapsed 65,536 lines", &many, [true, false], 1, [(65_536, 12), (65_536, 12)]);
    witness("missing part", &many, [true, true], 2, [(65_536, 12), (65_536, 12)]);
    let budget = "a".repeat(1_000) + &"x\n".repeat(500);
    assert_eq!(budget.len(), 2_000);
    witness("full 2,000 bytes, 500 lines", &budget, [true, false], 0, [(500, 12), (13, 0)]);
    witness("full 128 KiB, one line", &"z".repeat(131_072), [true, false], 0, [(1, 1), (0, 0)]);
    witness("full 12-line short block", &"x\r\n".repeat(12), [true, false], 0, [(12, 0), (12, 0)]);
}
