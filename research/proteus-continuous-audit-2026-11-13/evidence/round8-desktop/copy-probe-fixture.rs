#[derive(Clone)] struct Api;
struct Session { dir: PathBuf, transcript: crate::transcript::Transcript }
struct History;
impl History { fn copy_cursor(&self, _: &crate::transcript::Transcript) -> Option<AppTranscriptCursor> { None } }
struct Binding { archive: Option<crate::transcript::Transcript>, cursor_chain: Vec<Option<String>>, oldest_page: usize, handle: ThreadHandle }
struct Chat { transcript: crate::transcript::Transcript, codex: Option<Binding>, history: History, session: Session, api: Option<Api> }
impl Chat { fn display_transcript(&self) -> &crate::transcript::Transcript { &self.transcript } }

#[test]
fn round8_copy_final_response_loses_after_tool_text_from_duplicate_archive_key() {
    use crate::model_standard::{CanonicalMessage, ContentPart, MessageRole};
    let rows=crate::core_projection::transcript_messages(&[
        CanonicalMessage::text(MessageRole::User, "question"),
        CanonicalMessage::new(MessageRole::Assistant, vec![
            ContentPart::Text { text: "Before tool".into() },
            ContentPart::ToolCall { call: crate::domain::ToolCall::new("call-copy", "read_file", serde_json::json!({})) },
            ContentPart::Text { text: "After tool".into() },
        ])
    ]);
    let mut live=crate::transcript::Transcript::default();
    live.reset(rows.clone());
    let mut archive=crate::transcript::Transcript::default();
    archive.append_page(rows, &live);
    let end_key=archive.entries().last().unwrap().key;
    let chat=Chat { transcript: archive, codex: None, history: History, session: Session { dir: "/test".into(), transcript: Default::default() }, api: None };
    let plan=chat.turn_copy_plan(end_key).unwrap();
    assert!(plan.older.is_none());
    let actual=plan.parts.finish().unwrap();
    assert_eq!(actual,"Before tool");
    assert!(!actual.contains("After tool"));
    eprintln!("copy final response actual={actual:?}, expected=\"Before tool\\n\\nAfter tool\"");
}
