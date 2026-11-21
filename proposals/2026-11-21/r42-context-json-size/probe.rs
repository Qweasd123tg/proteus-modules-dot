// Scoped test crate: the complete production summarizer from each revision,
// the candidate's shared byte counter, and Proteus' thread-local test allocator.
pub(crate) use proteus_contracts::model_standard;
mod baseline;
mod candidate;
mod json_size;
mod test_alloc;

#[cfg(test)]
mod comparison {
    use crate::model_standard::{CanonicalMessage, ContentPart, MessageRole};
    use proteus_contracts::domain::{
        Citation, ContextChunk, HostedToolActivity, HostedToolStatus, ToolCall, ToolContent,
        ToolResult, WebSearchAction,
    };
    use serde_json::json;
    use std::hint::black_box;

    fn structured(n: usize, padding: usize) -> Vec<CanonicalMessage> {
        let mut msg = CanonicalMessage::new(
            MessageRole::Assistant,
            vec![
                ContentPart::Context {
                    chunk: ContextChunk::new("источник", "🦀".repeat(padding))
                        .with_metadata(json!({"quote": "\\\n\""})),
                },
                ContentPart::ToolCall {
                    call: ToolCall::new(
                        "c",
                        "inspect",
                        json!({"args": ["a\t\0中".repeat(n), 2.5, null]}),
                    ),
                },
                ContentPart::ToolResult {
                    result: ToolResult::ok("c".into(), "output")
                        .with_metadata(json!({"escaped": "a\n\r", "ok": true}))
                        .with_content(vec![
                            ToolContent::Text {
                                text: "x\n\u{0002}".repeat(n),
                            },
                            ToolContent::Image {
                                mime_type: "image/png".into(),
                                data: "YWJj".repeat(n),
                            },
                            ToolContent::Json {
                                value: json!([false, {"data":"z".repeat(n)}]),
                            },
                            ToolContent::Binary {
                                mime_type: "application/octet-stream".into(),
                                data: "AA==".repeat(n),
                            },
                        ]),
                },
                ContentPart::Citation {
                    citation: Citation::File {
                        index: 1,
                        file_id: "a".into(),
                        filename: "файл\n".into(),
                    },
                },
                ContentPart::HostedToolActivity {
                    activity: HostedToolActivity::WebSearch {
                        id: "s".into(),
                        status: HostedToolStatus::Completed,
                        action: WebSearchAction::OpenPage {
                            url: "https://example.org/🦀".into(),
                        },
                    },
                },
            ],
        );
        msg.metadata = json!({"escaped": "\"" .repeat(n)});
        vec![
            CanonicalMessage::text(MessageRole::User, "ж"),
            msg,
            CanonicalMessage::text(MessageRole::System, "a".repeat(padding)),
            CanonicalMessage::text(MessageRole::Developer, "d"),
        ]
    }

    #[test]
    fn same_summary_across_roles_escapes_and_estimate_rounding() {
        assert_eq!(
            crate::candidate::summarize_context_history(&[]),
            crate::baseline::summarize_context_history(&[])
        );
        for n in [0, 1, 31, 1001] {
            for pad in 0..4 {
                let input = structured(n, pad);
                assert_eq!(
                    crate::candidate::summarize_context_history(&input),
                    crate::baseline::summarize_context_history(&input)
                );
            }
        }
    }

    #[test]
    fn allocation_traffic_for_complete_history_summary() {
        let basic = (0..1000)
            .map(|_| CanonicalMessage::text(MessageRole::User, "ordinary plain text"))
            .collect::<Vec<_>>();
        for (name, input) in [
            ("plain_1000", basic),
            ("rich_1K", structured(1024, 1)),
            ("rich_128K", structured(131072, 1)),
        ] {
            let (old, before) = crate::test_alloc::measure(|| {
                crate::baseline::summarize_context_history(black_box(&input))
            });
            let (new, after) = crate::test_alloc::measure(|| {
                crate::candidate::summarize_context_history(black_box(&input))
            });
            assert_eq!(old, new);
            assert!(before.bytes > after.bytes && after.bytes < 1024);
            println!(
                "{name}: estimated_tokens={} allocation_bytes={}->{} allocation_calls={}->{}",
                new.estimated_tokens, before.bytes, after.bytes, before.calls, after.calls
            );
        }
    }
}
