// Included in packages/usage/src/main.rs in a disposable checkout instead of main.
// Production report::turn_ids and view::render are compiled and called unmodified.
use std::{hint::black_box, io::Write, time::Instant};

const CASES: [(usize, usize); 6] = [(0, 0), (32, 2), (2048, 16), (2048, 512), (8192, 2048), (8192, 8192)];

fn make_session(n: usize, cardinality: usize) -> Value {
    let requests = (0..n).map(|i| {
        let t = i % cardinality.max(1);
        proteus_extension::json!({
            "exchange_id":format!("req-{i}"), "turn_id":format!("ход-{t:08}"),
            "started_at_ms":i as i64, "finished_at_ms":i as i64+1,
            "model":{"provider":"fixture","model":"gpt-6-astra"},
            "status":if i%11 == 0 {"error"} else {"completed"},
            "usage":{"input_tokens":900,"output_tokens":30}
        })
    }).collect::<Vec<_>>();
    proteus_extension::json!({"latest_turn_id":"ход-00000001","requests":requests})
}

fn main() {
    let wire = std::env::args().nth(1).as_deref() == Some("wire");
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    for (n, cardinality) in CASES {
        let snapshot = make_session(n, cardinality);
        if wire {
            for mut state in [
                Usage::default(),
                Usage { status: "problems".into(), order: "newest".into(), page: 1, ..Usage::default() },
                Usage { period:"ход-00000001".into(), ..Usage::default() },
                Usage { period:"latest".into(), ..Usage::default() },
            ] {
                serde_json::to_writer(&mut out, &view::render(&mut state, &snapshot).unwrap()).unwrap();
                writeln!(&mut out).unwrap();
            }
        } else {
            let index = || { drop(black_box(report::turn_ids(black_box(&snapshot)))); };
            let render = || { drop(black_box(view::render(&mut Usage::default(), black_box(&snapshot)).unwrap())); };
            let timed = |f: &dyn Fn(), reps: u32| {
                f(); // untimed warm-up
                let before = Instant::now();
                for _ in 0..reps { f(); }
                before.elapsed().as_nanos() / reps as u128
            };
            let k = if n <= 32 { 500 } else if n <= 2048 { 7 } else { 1 };
            writeln!(&mut out, "{n}\t{cardinality}\t{}\t{}", timed(&index, k), timed(&render, k.min(4))).unwrap();
        }
    }
}
