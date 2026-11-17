use serde::{Deserialize, Serialize};
use std::io::{self, BufRead};
use std::path::PathBuf;
//DECLARATIONS
#[derive(Deserialize)]
struct Case {
    label: String,
    index: serde_json::Value,
    valid_index: bool,
    expected: Vec<bool>,
}
fn main() {
    let mut cases = 0;
    let mut rows = 0;
    for line in io::stdin().lock().lines() {
        let c: Case = serde_json::from_str(&line.unwrap()).unwrap();
        let parsed = serde_json::from_value::<Index>(c.index);
        assert_eq!(parsed.is_ok(), c.valid_index);
        if let Ok(i) = parsed {
            assert_eq!(i.format, 1);
            let accepted = i
                .entries
                .into_iter()
                .map(|x| serde_json::from_value::<Entry>(x).is_ok())
                .collect::<Vec<_>>();
            assert_eq!(accepted, c.expected);
            rows += accepted.len();
            println!(
                "{}: {}/{} entries match schema.",
                c.label,
                accepted.iter().filter(|x| **x).count(),
                accepted.len()
            );
        } else {
            println!("{}: rejected at index level.", c.label);
        }
        cases += 1;
    }
    println!(
        "{cases} catalog inputs, {rows} entries checked; no build, filesystem discovery, profile, install or running app used."
    );
}
