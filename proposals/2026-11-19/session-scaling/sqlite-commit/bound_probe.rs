
#[test]
#[ignore = "standalone exact canonical byte-limit probe; allocates large payloads"]
fn perf6_canonical_commit_byte_limit() {
    use crate::codec::canonicalize_entry;
    use crate::io::MAX_PAYLOAD_BYTES;
    use proteus_contracts::model_standard::ContentPart;
    let make = || JournalEntry::HistoryMutated(HistoryMutated {
        previous_revision: 0, new_revision: 1, mutation: HistoryMutationKind::Append,
        messages: vec![text("escape\n\"utf8 世界\\")], compaction: None, tool_results: vec![],
    });
    let overhead = serde_json::to_vec(&make().payload_value().unwrap()).unwrap().len();
    for (target, accept) in [(MAX_PAYLOAD_BYTES, true), (MAX_PAYLOAD_BYTES + 1, false)] {
        let mut entry = make();
        let JournalEntry::HistoryMutated(change) = &mut entry else { unreachable!() };
        let ContentPart::Text { text } = &mut change.messages[0].parts[0].payload else { unreachable!() };
        text.extend(std::iter::repeat_n('x', target - overhead));
        let checked = canonicalize_entry(PROBE_BORROWentry);
        if accept { assert!(checked.is_ok()); } else { assert_eq!(checked.unwrap_err().to_string(), "journal payload exceeds maximum"); }
    }
}
