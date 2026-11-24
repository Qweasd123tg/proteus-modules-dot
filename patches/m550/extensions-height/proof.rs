#[cfg(test)]
mod m550_disclosure_checks {
    use super::*;
    use serde_json::json;
    use std::fs;
    use crate::{details::step_card, summary::turn_summary};

    #[test]
    fn saturated_wire_and_unsaturated_frontier() {
        let row = format!("{}\u{2029}", "🦀".repeat(110));
        let frontier = row.repeat(19);
        assert_eq!(frontier.len(), 8417);
        let mut fixtures = vec![
            (frontier.clone(), 358),
            (format!("{frontier}x"), 360),
            ("\r\n".repeat(19), 358),
            ("\r\n".repeat(20), 360),
            ("λ".repeat(2090), 358),
            ("x".repeat(2091), 360),
        ];
        for sep in ["\n", "\r", "\r\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\u{85}", "\u{2028}", "\u{2029}"] {
            fixtures.push((format!("{}{sep}", "🦀".repeat(110)).repeat(19), 358));
            fixtures.push((format!("{}{sep}", "🦀".repeat(110)).repeat(20), 360));
        }
        for (text, want) in fixtures {
            let node = disclosure("1:args", "x", &json!(text), &Open);
            assert_eq!(node["children"][0]["height"], want);
            assert_eq!(node["children"][0]["text"], text);
        }
        assert_eq!(height(&"x".repeat(1_500_000), false), 48);
        let huge = "🦀\0я".repeat(100_000);
        let step = json!({"sequence":4,"data":{"kind":"tool","call":{"id":"id","args":{"arg":true}},"result":{"output":huge}}});
        let turn = json!({"turn_id":"id","task":{"text":huge}});
        let a = step_card(&step, &Open);
        let b = turn_summary(&turn, &json!(2), &json!("complete"), &Open);
        let bytes = serde_json::to_vec(&[a, b]).unwrap();
        assert!(bytes.len() > 2_000_000);
        fs::write(std::env::var("EXT_SNAPSHOT").unwrap(), bytes).unwrap();
    }
}
