// Loaded under each copy of the original production module so setup can seed
// the private pending receipt set without a subprocess or a second parser.
use super::*;
use crate::test_alloc::{Allocations, measure};
use serde_json::json;

pub(crate) fn run(
    id: &str,
    ok: bool,
    mut output: Option<Value>,
    error: Option<&str>,
) -> (Value, Allocations, Option<Value>) {
    let mut tracker = PeerMessageDelivery::default();
    tracker.pending_receipts.insert("receipt".into());
    let (response, stats) = measure(|| call_confirm(&mut tracker, id, ok, &mut output, error));
    let mut projected = match response {
        Ok(None) => json!({"kind":"unrelated"}),
        Ok(Some(PeerMessageResponse::Queued)) => json!({"kind":"queued"}),
        Ok(Some(PeerMessageResponse::TurnCompleted(answer))) => {
            json!({"kind":"complete", "answer":answer})
        }
        Err(error) => {
            json!({"kind":"error","chain":error.chain().map(ToString::to_string).collect::<Vec<_>>()})
        }
    };
    projected["settled"] = Value::Bool(tracker.is_settled());
    assert_eq!(tracker.is_settled(), id == "receipt");
    let mut duplicate = Some(json!({"text":"duplicate","metadata":null}));
    assert!(
        call_confirm(&mut tracker, id, true, &mut duplicate, None)
            .unwrap()
            .is_none()
    );
    assert!(
        duplicate.is_some(),
        "unrelated or duplicate IDs cannot take ownership"
    );
    (projected, stats, output)
}
