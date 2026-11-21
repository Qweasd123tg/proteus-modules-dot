mod encoder;
mod ledger;
mod stream;

use proteus_contracts::app_protocol::{
    AppServerEvent, AppSessionSnapshot, AppTranscriptCursor, AppTranscriptMessage, StdioOutput,
};
use proteus_contracts::domain::{Event, EventEnvelope};
use serde_json::{Value, json};
use std::io::{self, Cursor, Read};
use stream::{StreamItem, for_fixture};
use uuid::Uuid;

fn output(event: AppServerEvent) -> StdioOutput {
    StdioOutput::Event {
        event: Box::new(event),
    }
}

fn snapshot(session: u128) -> StdioOutput {
    output(AppServerEvent::SessionSnapshot {
        snapshot: Box::new(AppSessionSnapshot {
            session_id: Uuid::from_u128(session),
            stream_id: format!("fixture-{session}"),
            seq: 5,
            root_thread_id: Some(Uuid::from_u128(session + 0x100)),
            transcript: (0..50)
                .map(|i| AppTranscriptMessage {
                    message_id: Some(Uuid::from_u128(i + 0x1000)),
                    timestamp_ms: Some(1000 + i as i64),
                    phase: None,
                    role: if i % 2 == 0 { "assistant" } else { "user" }.into(),
                    text: format!("{} {i} \"\n", "Текст окна λ🦀 ".repeat(48)),
                    images: vec![],
                    tool: None,
                    subagent: None,
                    streaming: false,
                })
                .collect(),
            history: Some(AppTranscriptCursor {
                revision: "fixture-revision".into(),
                before: 2000,
                base: None,
            }),
            execution: Default::default(),
        }),
    })
}

fn delta(session: u128, seq: u64) -> StdioOutput {
    let text = "Слово λ🦀\n";
    // The pinned EventEnvelope is non-exhaustive. Validate full typed wire
    // fields with Serde rather than a constructor with wall time / random IDs.
    let envelope: EventEnvelope = serde_json::from_value(json!({
        "schema_version": 2,
        "event_id": Uuid::from_u128(session * 1000 + seq as u128),
        "session_id": Uuid::from_u128(session),
        "thread_id": Uuid::from_u128(session + 0x100),
        "turn_id": Uuid::from_u128(session + 0x200),
        "seq": seq,
        "timestamp_ms": 10000 + seq as i64,
        "event": Event::AssistantTextDelta {
            offset: (seq as usize - 6) * text.len(),
            message_id: Uuid::from_u128(0x3000 + session),
            phase: None,
            text: text.into()
        }
    }))
    .unwrap();
    output(AppServerEvent::Runtime {
        envelope: Box::new(envelope),
    })
}

fn wire(out: &mut Vec<u8>, value: &StdioOutput) -> usize {
    // The exact pinned Core encoder, not a mock wire decoder.
    let frame = encoder::encode_sse_output(value);
    let compact = frame
        .strip_prefix(b"event: output\ndata: ")
        .and_then(|bytes| bytes.strip_suffix(b"\n\n"))
        .unwrap();
    assert_eq!(compact, serde_json::to_vec(value).unwrap().as_slice());
    let count = compact.len();
    out.extend_from_slice(&frame);
    count
}

fn each_result(reader: impl Read + Send + 'static, capacity: usize, limit: usize) -> Vec<Value> {
    let mut s = for_fixture(capacity, reader);
    (0..limit)
        .map(|_| match s.next() {
            Some(Ok(StreamItem::Event(event))) => json!({"event": event}),
            Some(Ok(StreamItem::Heartbeat)) => json!({"heartbeat": true}),
            Some(Err(error)) => {
                let kind = error
                    .downcast_ref::<io::Error>()
                    .map(|err| format!("{:?}", err.kind()));
                json!({"error": error.to_string(), "kind": kind})
            }
            None => json!({"eof": true}),
        })
        .collect()
}

fn canonical_expected(frame: &StdioOutput) -> Value {
    let StdioOutput::Event { event } = frame else {
        unreachable!()
    };
    json!({"event": event})
}

fn report(name: &str, got: Vec<Value>, copied: usize, expected: usize) {
    assert_eq!(copied, expected, "{name}");
    for item in got {
        println!("{name}\t{item}");
    }
    eprintln!("WORK {name} explicit_payload_append_bytes={copied}");
}

fn normal(which: u128, candidate: bool) {
    let frames: Vec<_> = std::iter::once(snapshot(which))
        .chain((6..38).map(|seq| delta(which, seq)))
        .collect();
    let mut out = b": keep-alive\n\n".to_vec();
    let bytes: usize = frames.iter().map(|value| wire(&mut out, value)).sum();
    assert_eq!(ledger::take(), 0);
    let got = each_result(Cursor::new(out), 8192, frames.len() + 2);
    assert_eq!(got[0], json!({"heartbeat": true}));
    for (decoded, expected) in got[1..].iter().zip(&frames) {
        assert_eq!(*decoded, canonical_expected(expected));
    }
    assert_eq!(got.last(), Some(&json!({"eof": true})));
    report(
        &format!("chat-{which}"),
        got,
        ledger::take(),
        if candidate { 0 } else { bytes },
    );
}

fn multiline(candidate: bool) {
    let value = delta(40, 6);
    let pretty = serde_json::to_string_pretty(&value).unwrap();
    let mut out = b"\r\ndata:\r\n:empty-then-heartbeat\r\n\r\nid: 3\r\n".to_vec();
    let (mut first, mut rest) = (0, 0);
    for (i, line) in pretty.lines().enumerate() {
        // A comment and an ignored non-data field after a payload cannot
        // break a retained event. An empty continuation adds one newline.
        if i == 1 {
            out.extend_from_slice(b": inside-payload\r\nretry: 44\r\ndata: \r\n");
        }
        if i == 0 {
            first = line.len();
        } else {
            rest += line.len();
        }
        out.extend_from_slice(b"data: ");
        out.extend_from_slice(line.as_bytes());
        out.extend_from_slice(b"\r\n");
    }
    out.extend_from_slice(b"\r\n");
    let got = each_result(Cursor::new(out), 5, 3);
    assert_eq!(
        got,
        [
            json!({"heartbeat": true}),
            canonical_expected(&value),
            json!({"eof": true})
        ]
    );
    report(
        "multiline",
        got,
        ledger::take(),
        if candidate { rest } else { first + rest },
    );
}

struct Broken(Cursor<Vec<u8>>);
impl Read for Broken {
    fn read(&mut self, dst: &mut [u8]) -> io::Result<usize> {
        let count = self.0.read(dst)?;
        if count == 0 {
            Err(io::Error::other("fixture read failed"))
        } else {
            Ok(count)
        }
    }
}
fn negative(candidate: bool) {
    let value = delta(40, 6);
    let mut incomplete = Vec::new();
    let bytes = wire(&mut incomplete, &value);
    incomplete.pop(); // no blank separator, even though a complete data line is present
    let got = each_result(Cursor::new(incomplete.clone()), 7, 1);
    assert_eq!(got, [json!({"eof": true})]);
    report(
        "incomplete",
        got,
        ledger::take(),
        if candidate { 0 } else { bytes },
    );
    let got = each_result(Broken(Cursor::new(incomplete)), 7, 1);
    assert_eq!(got, [json!({"error":"fixture read failed","kind":"Other"})]);
    report(
        "read-error",
        got,
        ledger::take(),
        if candidate { 0 } else { bytes },
    );

    let invalid = b"data: \xff\n\n".to_vec();
    let got = each_result(Cursor::new(invalid), 4, 1);
    assert_eq!(got[0]["kind"], "InvalidData");
    report("invalid-utf8", got, ledger::take(), 0);
    let got = each_result(Cursor::new(b"data:  \n\n".to_vec()), 4, 2);
    assert!(got[0]["error"].is_string());
    assert_eq!(got[1], json!({"eof":true}));
    report(
        "ascii-space-only",
        got,
        ledger::take(),
        if candidate { 0 } else { 1 },
    );
    for (label, error, want) in [
        (
            "response-error",
            Some("fixture error".into()),
            "event stream failed: fixture error",
        ),
        (
            "response-empty",
            None,
            "unexpected response on the event stream",
        ),
    ] {
        let mut body = Vec::new();
        let bytes = wire(
            &mut body,
            &StdioOutput::Response {
                id: None,
                ok: false,
                output: None,
                error,
            },
        );
        let got = each_result(Cursor::new(body), 16, 2);
        assert_eq!(got[0]["error"], want);
        assert_eq!(got[1], json!({"eof":true}));
        report(
            label,
            got,
            ledger::take(),
            if candidate { 0 } else { bytes },
        );
    }
}

fn capacity_control() {
    ledger::take_peak();
    assert_eq!(ledger::take(), 0);
    let mut input = b"ignored: ".to_vec();
    // Benign unused SSE fields intentionally larger than the following payload.
    let large = b'a';
    input.extend(std::iter::repeat_n(large, 128 * 1024));
    input.push(b'\n');
    let value = delta(77, 6);
    let frame = encoder::encode_sse_output(&value);
    let data_line = frame
        .strip_prefix(b"event: output\n")
        .unwrap()
        .strip_suffix(b"\n")
        .unwrap();
    input.extend_from_slice(data_line);
    input.extend_from_slice(b"ignored: ");
    input.extend(std::iter::repeat_n(large, 128 * 1024));
    input.extend_from_slice(b"\n\n");
    let got = each_result(Cursor::new(input), 8192, 2);
    assert_eq!(got, [canonical_expected(&value), json!({"eof":true})]);
    let copied = data_line
        .strip_prefix(b"data: ")
        .unwrap()
        .strip_suffix(b"\n")
        .unwrap()
        .len();
    report("retained-scratch", got, ledger::take(), copied);
    let capacity = ledger::take_peak();
    assert!(capacity >= 128 * 1024);
    eprintln!("CAPACITY retained-scratch simultaneous_string_capacity={capacity}");
}

fn main() {
    let arm = env!("R75_SSE_PROBE_ARM");
    eprintln!("ARM {arm}");
    let candidate = arm.ends_with("/candidate");
    normal(1, candidate);
    normal(2, candidate);
    multiline(candidate);
    negative(candidate);
    capacity_control();
}
