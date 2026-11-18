//! A pure fenced-source -> public widget tree. No I/O or extension context.
use serde_json::{Value, json};
use std::collections::HashMap;

fn message(s: impl Into<String>) -> Value {
    json!({"type":"text","text":s.into()})
}

/// Counts use ASCII decimal digits; groups are case-sensitive and ordered by
/// first occurrence. A malformed line never returns a partial result.
pub fn render(source: &str) -> Value {
    let mut seen = HashMap::<&str, usize>::new();
    let mut rows: Vec<(&str, u64)> = Vec::new();
    let mut total = 0_u64;
    for (i, raw) in source.lines().enumerate() {
        let line = raw.trim();
        if line.is_empty() {
            continue;
        }
        let fail = |reason: &str| message(format!("Line {}: {reason}", i + 1));
        let Some((label, raw_count)) = line.split_once(':') else {
            return fail("expected label: count");
        };
        let (label, count) = (label.trim(), raw_count.trim());
        if label.is_empty() {
            return fail("label is empty");
        }
        if count.is_empty() || !count.bytes().all(|c| c.is_ascii_digit()) {
            return fail("use one non-negative whole count after the colon");
        }
        let Ok(count) = count.parse::<u64>() else {
            return fail("count is too large");
        };
        let Some(next) = total.checked_add(count) else {
            return fail("total is too large");
        };
        total = next;
        let index = *seen.entry(label).or_insert_with(|| {
            rows.push((label, 0));
            rows.len() - 1
        });
        // Every group subtotal is bounded by the just-checked total.
        rows[index].1 += count;
    }
    if rows.is_empty() {
        return message("No counts yet. Try Paper: 3");
    }
    let rows: Vec<_> = rows
        .into_iter()
        .map(|(label, n)| [label.to_owned(), n.to_string()])
        .collect();
    json!({"type":"card","title":format!("Total: {total}"),"children":[
        {"type":"table","columns":["Item","Count"],"rows":rows}
    ]})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn repeated_names_are_added_in_first_seen_order() {
        assert_eq!(
            render("Paper: 3\nInk: 2\nPaper: 4"),
            json!({"type":"card","title":"Total: 9","children":[{"type":"table","columns":["Item","Count"],"rows":[["Paper","7"],["Ink","2"]]}]})
        );
    }
    #[test]
    fn blank() {
        assert_eq!(render(" \n\t\r\n"), message("No counts yet. Try Paper: 3"));
    }
    #[test]
    fn ambiguous_colon_and_bad_counts_fail_on_the_real_line() {
        for bad in ["a: b: 2", "a: -3", "a: 1.3", "a:", "a: +2"] {
            assert_eq!(
                render(&format!("OK: 0\n\n{bad}")),
                message("Line 3: use one non-negative whole count after the colon")
            );
        }
        assert_eq!(render("missing"), message("Line 1: expected label: count"));
        assert_eq!(render(": 2"), message("Line 1: label is empty"));
    }
    #[test]
    fn trimmed_unicode_names_but_case_sensitive() {
        assert_eq!(
            render(" 東京 : 1\r\nTotal: 02\r\n東京: 2\r\ntotal: 0")["children"][0]["rows"],
            json!([["東京", "3"], ["Total", "2"], ["total", "0"]])
        );
    }
    #[test]
    fn reports_numeric_limits_without_partial_table() {
        assert_eq!(
            render("x: 18446744073709551616"),
            message("Line 1: count is too large")
        );
        assert_eq!(
            render("x: 18446744073709551615\ny: 1"),
            message("Line 2: total is too large")
        );
        assert_eq!(
            render("x: 18446744073709551615")["title"],
            "Total: 18446744073709551615"
        );
    }
}
