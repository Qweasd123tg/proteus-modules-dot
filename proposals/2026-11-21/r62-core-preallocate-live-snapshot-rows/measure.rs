pub use proteus_contracts::{contracts, domain, model_standard};

mod transcript {
    pub use proteus_contracts::app_protocol::{
        AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool,
    };
}

#[path = "candidate_harness/mod.rs"]
mod candidate;
#[path = "stock_harness/mod.rs"]
mod stock;
mod test_alloc;

use std::{hint::black_box, io::Write as _};

use domain::ImageRef;
use model_standard::MessagePhase;
use serde_json::json;
use transcript::{AppTranscriptMessage as Row, AppTranscriptSubagent, AppTranscriptTool};
use uuid::Uuid;

#[derive(Clone)]
struct Fixture {
    messages: Vec<Row>,
    submitted: Option<String>,
    submitted_at: Option<i64>,
    submitted_images: Vec<ImageRef>,
    failed: Vec<Row>,
    background: Vec<Row>,
}

fn image(id: usize) -> ImageRef {
    ImageRef {
        id: format!("synthetic-{id}"),
        name: format!("图像-{id}.png"),
        mime_type: "image/png".into(),
        path: format!("images/fixture-{id}.png").into(),
    }
}

fn row(id: usize, role: &str) -> Row {
    Row {
        timestamp_ms: (id % 2 == 0).then_some(-(id as i64)),
        images: if id % 5 == 0 { vec![image(id)] } else { vec![] },
        message_id: Some(Uuid::from_u128(id as u128)),
        phase: match id % 3 {
            0 => Some(MessagePhase::Commentary),
            1 => Some(MessagePhase::FinalAnswer),
            _ => None,
        },
        role: role.into(),
        text: match id % 3 {
            0 => format!("😀\nстрока {id}\0"),
            1 => format!("visible-{id}"),
            _ => String::new(),
        },
        tool: None,
        subagent: None,
        streaming: false,
    }
}

fn tool(id: usize) -> AppTranscriptTool {
    AppTranscriptTool {
        terminal: None,
        call_id: format!("fixture-call-{id}"),
        name: "fixture-read".into(),
        args: json!({"path":"demo", "i":id}),
        effective_args: Some(json!({"path":"demo/effective"})),
        status: "done".into(),
        result: Some("returned value".into()),
        metadata: json!({"shape":["x", null, true]}),
    }
}

fn fixture(live: usize, submission: usize, failed: usize, background: usize) -> Fixture {
    let mut messages = (0..live)
        .map(|i| {
            let mut r = row(
                i + 1,
                match i % 4 {
                    0 => "user",
                    1 => "reasoning",
                    2 => "system",
                    _ => "assistant",
                },
            );
            if i % 4 == 2 {
                r.tool = Some(tool(i));
            }
            r
        })
        .collect::<Vec<_>>();
    if let Some(row) = messages.last_mut() {
        row.streaming = true;
    }
    let failed = (0..failed).map(|i| row(200 + i, "user")).collect();
    let background = (0..background)
        .map(|i| {
            let mut r = row(300 + i, "system");
            r.message_id = None;
            r.text.clear();
            r.subagent = Some(AppTranscriptSubagent {
                child_thread_id: Uuid::from_u128(300 + i as u128).to_string(),
                session: None,
                role: "helper".into(),
                description: Some(format!("fixture {i}")),
                status: if i % 2 == 0 { "running" } else { "completed" }.into(),
                iterations: Some(1),
                tools: vec![tool(300 + i)],
            });
            r
        })
        .collect();
    Fixture {
        messages,
        submitted: match submission {
            0 => None,
            1 => Some("typed new prompt\n😀\0".into()),
            _ => Some(String::new()),
        },
        submitted_at: (submission == 1).then_some(73),
        submitted_images: if submission == 2 {
            vec![image(42), image(43)]
        } else {
            vec![]
        },
        failed,
        background,
    }
}

#[test]
fn byte_parity_all_group_combinations() {
    let file = std::fs::File::create(std::env::var_os("R62_SNAPSHOT").unwrap()).unwrap();
    let mut out = std::io::BufWriter::new(file);
    let mut count = 0;
    for live in [0, 1, 3, 8] {
        for submission in 0..3 {
            for failed in [0, 1, 4, 32] {
                for background in [0, 1, 2, 64] {
                    let fixture = fixture(live, submission, failed, background);
                    let before = stock::State::new(fixture.clone()).snapshot();
                    let after = candidate::State::new(fixture).snapshot();
                    let old_bytes = serde_json::to_vec(&before).unwrap();
                    let new_bytes = serde_json::to_vec(&after).unwrap();
                    assert_eq!(
                        old_bytes, new_bytes,
                        "{live}/{submission}/{failed}/{background}"
                    );
                    assert_eq!(
                        after.len(),
                        live + usize::from(submission != 0) + failed + background
                    );
                    out.write_all(&(new_bytes.len() as u64).to_le_bytes())
                        .unwrap();
                    out.write_all(&new_bytes).unwrap();
                    count += 1;
                }
            }
        }
    }
    out.flush().unwrap();
    assert_eq!(count, 192);
    println!("{count} byte-identical live snapshots");
}

#[test]
fn cloned_snapshot_has_published_order_and_independent_nested_data() {
    let state = candidate::State::new(fixture(4, 2, 3, 2));
    let mut first = state.snapshot();
    assert_eq!(
        first.iter().map(|r| r.role.as_str()).collect::<Vec<_>>(),
        [
            "user",
            "reasoning",
            "system",
            "assistant",
            "user",
            "user",
            "user",
            "user",
            "system",
            "system"
        ]
    );
    assert!(first[3].streaming);
    assert!(first[4].text.is_empty());
    assert_eq!(first[4].timestamp_ms, None);
    assert_eq!(first[4].images[0].id, "synthetic-42");
    assert_eq!(first[5].message_id, Some(Uuid::from_u128(200)));
    assert!(first[8].subagent.as_ref().is_some());
    let old_bytes = serde_json::to_vec(&first).unwrap();
    first[4].images[0].id.clear();
    first[8].subagent.as_mut().unwrap().tools[0].metadata = json!({"edited":true});
    assert_eq!(serde_json::to_vec(&state.snapshot()).unwrap(), old_bytes);
}

#[test]
fn snapshot_allocation_requests() {
    let mut demonstrated = false;
    for (case, input) in [
        ("empty", fixture(0, 0, 0, 0)),
        ("active-without-tail", fixture(8, 0, 0, 0)),
        ("one-submitted", fixture(0, 1, 0, 0)),
        ("active-with-child-cards", fixture(8, 0, 0, 2)),
        ("prep-failure-with-children", fixture(0, 2, 3, 2)),
        ("bounded-tail-stress", fixture(4, 0, 32, 64)),
    ] {
        let before = stock::State::new(input.clone());
        let after = candidate::State::new(input);
        let (a, old) = test_alloc::measure(|| black_box(black_box(&before).snapshot()));
        let (b, new) = test_alloc::measure(|| black_box(black_box(&after).snapshot()));
        assert_eq!(
            serde_json::to_vec(&a).unwrap(),
            serde_json::to_vec(&b).unwrap()
        );
        assert_eq!(b.capacity(), b.len());
        assert!(new.calls <= old.calls && new.bytes <= old.bytes, "{case}");
        if case == "active-with-child-cards" {
            assert!(new.calls < old.calls && new.bytes < old.bytes);
            demonstrated = true;
        }
        println!(
            "{case:27} requests {:4} -> {:4}, bytes {:7} -> {:7}, row capacity {:3} -> {:3} (len {})",
            old.calls,
            new.calls,
            old.bytes,
            new.bytes,
            a.capacity(),
            b.capacity(),
            a.len()
        );
    }
    assert!(demonstrated);
}
