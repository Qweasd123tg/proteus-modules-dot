// Independent typed visitor/codec oracle. These records are supplied at the
// visitor boundary; the separate large route exercises actual validation/I/O.
use super::PrefixIdentities;
use proteus_contracts::{
    contracts::WorkflowToolResultBinding,
    domain::{
        Citation, HostedToolActivity, SubagentSessionBinding, ToolCall, ToolCallResolution,
        ToolResult,
    },
    model_standard::{
        CanonicalMessage, CanonicalModelResponse, CanonicalPart, ContentPart, FinishReason,
        MessageRole, PartProvenance, PartScope,
    },
    storage::journal::*,
};
use serde_json::json;
use std::collections::HashSet;
use uuid::Uuid;
fn id(x: u128) -> Uuid {
    Uuid::from_u128(x)
}
fn ids(xs: &[u128]) -> HashSet<Uuid> {
    xs.iter().copied().map(id).collect()
}
fn names(xs: &[&str]) -> HashSet<String> {
    xs.iter().map(|x| (*x).to_owned()).collect()
}
fn part(x: u128, payload: ContentPart, scope: PartScope) -> CanonicalPart {
    CanonicalPart::new(PartProvenance::Model, scope, payload).with_id(id(x))
}
fn text(x: u128, scope: PartScope) -> CanonicalPart {
    part(
        x,
        ContentPart::Text {
            text: format!("owner-{x}"),
        },
        scope,
    )
}
fn message(x: u128, parts: Vec<CanonicalPart>) -> CanonicalMessage {
    CanonicalMessage::from_parts(MessageRole::Assistant, parts).with_id(id(x))
}
fn call(x: &str) -> ToolCall {
    ToolCall::new(x, "find", json!({"ψ": ["a", 1]}))
}
fn result(x: &str) -> ToolResult {
    ToolResult::ok(x.to_owned(), format!("result-{x}"))
}
fn rec(seq: u64, turn: u128, entry: JournalEntry) -> JournalRecord {
    JournalRecord {
        schema_version: JOURNAL_SCHEMA_VERSION,
        record_id: id(seq as u128 + 999),
        session_seq: seq,
        timestamp_ms: seq as i64,
        session_id: id(900),
        execution_id: None,
        thread_id: Some(id(901)),
        turn_id: Some(id(turn)),
        entry,
    }
}
fn history(
    seq: u64,
    turn: u128,
    mutation: HistoryMutationKind,
    messages: Vec<CanonicalMessage>,
) -> JournalRecord {
    let ignored = WorkflowToolResultBinding::new(call("binding-only"));
    rec(
        seq,
        turn,
        JournalEntry::HistoryMutated(HistoryMutated {
            previous_revision: seq.saturating_sub(1),
            new_revision: seq,
            mutation,
            messages,
            compaction: None,
            tool_results: vec![ignored],
        }),
    )
}
fn identical(a: &PrefixIdentities, b: &PrefixIdentities) {
    assert_eq!(a.history, b.history);
    assert_eq!(a.turns, b.turns);
    assert_eq!(a.exchanges, b.exchanges);
    assert_eq!(a.messages, b.messages);
    assert_eq!(a.parts, b.parts);
    assert_eq!(a.explicit_committed_parts, b.explicit_committed_parts);
    assert_eq!(a.calls, b.calls);
}
pub(crate) fn semantic_test() {
    let c: Citation=serde_json::from_value(json!({"type":"url","start_index":0,"end_index":1,"title":"example","url":"https://example.com"})).unwrap();
    let c_part = ContentPart::Citation { citation: c };
    let hosted:HostedToolActivity=serde_json::from_value(json!({"kind":"web_search","id":"hosted","status":{"state":"completed"},"action":{"type":"search","queries":["q"],"sources":[]}})).unwrap();
    let orig = message(
        10,
        vec![
            text(100, PartScope::Trace),
            part(
                101,
                ContentPart::ToolCall {
                    call: call("message-call"),
                },
                PartScope::Conversation,
            ),
            part(
                102,
                ContentPart::HostedToolActivity { activity: hosted },
                PartScope::Conversation,
            ),
            part(103, c_part.clone(), PartScope::Conversation),
        ],
    );
    let rehosted = message(
        11,
        vec![
            text(100, PartScope::Conversation),
            text(104, PartScope::Request),
        ],
    );
    let hidden_provider = message(12, vec![text(105, PartScope::Trace)]);
    let provider = message(13, vec![text(106, PartScope::Conversation)]);
    let canonical = message(
        14,
        vec![part(
            107,
            ContentPart::ToolResult {
                result: result("message-result"),
            },
            PartScope::Conversation,
        )],
    );
    let records = vec![
        history(
            1,
            1,
            HistoryMutationKind::Append,
            vec![orig.clone(), rehosted.clone()],
        ),
        rec(
            2,
            2,
            JournalEntry::ModelMessageRecorded(ModelMessageRecorded {
                exchange_id: id(80),
                message: hidden_provider,
            }),
        ),
        history(
            3,
            1,
            HistoryMutationKind::Replace,
            vec![rehosted.clone(), orig],
        ),
        rec(
            4,
            2,
            JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
                exchange_id: id(81),
                outcome: ModelResponseOutcome::Response {
                    response: CanonicalModelResponse::new(
                        provider,
                        vec![call("model-response")],
                        FinishReason::ToolCalls,
                    ),
                },
            }),
        ),
        history(
            5,
            3,
            HistoryMutationKind::Checkpoint,
            vec![rehosted, canonical],
        ),
        rec(
            6,
            3,
            JournalEntry::ToolCallRecorded(ToolCallRecorded {
                call: call("tool-record"),
                phase: ToolCallRecordPhase::Resolved {
                    resolution: ToolCallResolution::Allowed,
                },
            }),
        ),
        rec(
            7,
            3,
            JournalEntry::ToolResultRecorded(ToolResultRecorded {
                result: result("tool-result-record"),
            }),
        ),
        rec(
            8,
            4,
            JournalEntry::ToolEffectRecorded(ToolResultRecorded {
                result: result("tool-effect-record"),
            }),
        ),
        rec(
            9,
            4,
            JournalEntry::SubagentSessionBoundRecorded(SubagentSessionBinding {
                source_call_id: "subagent".into(),
                child_thread_id: id(812),
                session_id: id(813),
                session_dir: "/test".into(),
            }),
        ),
        rec(
            10,
            5,
            JournalEntry::TurnSettled(TurnSettled {
                status: TurnSettlementStatus::Success,
                output: None,
                error: None,
            }),
        ),
    ];
    let mut stock = PrefixIdentities::default();
    let mut candidate = PrefixIdentities::default();
    for r in records {
        assert!(stock.visit(&r, false));
        candidate.visit_owned_prefix(r);
        identical(&stock, &candidate);
    }
    assert_eq!(stock.turns, ids(&[1, 2, 3, 4, 5]));
    assert_eq!(stock.exchanges, ids(&[80, 81]));
    assert_eq!(stock.messages, ids(&[10, 11, 12, 13, 14]));
    assert_eq!(stock.parts, ids(&[100, 101, 102, 103, 104, 105, 106, 107]));
    assert_eq!(
        stock.explicit_committed_parts,
        ids(&[100, 101, 102, 103, 104, 107])
    );
    assert_eq!(
        stock.calls,
        names(&[
            "message-call",
            "message-result",
            "hosted",
            "model-response",
            "tool-record",
            "tool-result-record",
            "tool-effect-record",
            "subagent"
        ])
    );
    stock.history = vec![[91; 32], [1; 32], [91; 32]];
    candidate.history = stock.history.clone();
    let prev: PrefixIdentities =
        serde_json::from_slice(&serde_json::to_vec(&stock).unwrap()).unwrap();
    for prefix in [&stock, &candidate] {
        // Both byte encodings roundtrip with real decoders. HashSet iteration order
        // may differ, so compare all semantic sets and the exact ordered digest bytes.
        let direct: PrefixIdentities =
            serde_json::from_slice(&serde_json::to_vec(prefix).unwrap()).unwrap();
        identical(&direct, &prev);
        let packed = serde_json::to_value(prefix.encode_cache().unwrap()).unwrap();
        assert_eq!(packed["format"], 1);
        let decoded = PrefixIdentities::decode_cache(packed).unwrap();
        identical(&decoded, &prev);
    }
    let mut suffix = history(
        11,
        3,
        HistoryMutationKind::Append,
        vec![message(
            30,
            vec![
                text(120, PartScope::Request),
                part(121, c_part, PartScope::Conversation),
            ],
        )],
    );
    assert!(!stock.visit(&suffix, true));
    assert!(!candidate.visit_candidate(&suffix, true));
    suffix.turn_id = Some(id(49));
    assert!(!stock.visit(&suffix, true));
    assert!(!candidate.visit_candidate(&suffix, true)); // citation dependency, not a repeated turn
    let JournalEntry::HistoryMutated(x) = &mut suffix.entry else {
        unreachable!()
    };
    x.messages[0].parts.pop();
    assert!(stock.visit(&suffix, true));
    assert!(candidate.visit_candidate(&suffix, true));
    identical(&stock, &prev);
    identical(&candidate, &prev);
    println!(
        "{}",
        json!({"route":"codec","kind":"identity","fault":"ok","n":0,"passed":true,"records":10,"meters":{"stock":null,"candidate":null}})
    );
}
