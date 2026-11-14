//! Click-time copy reads a whole response without expanding the visible cache.
use std::{collections::HashSet, path::PathBuf, sync::Arc};

use anyhow::{Result, anyhow, bail, ensure};
use proteus_contracts::app_protocol::{AppTranscriptCursor, AppTranscriptPage};


use crate::{
    agents::codex::{Item, ItemKind, Page, ThreadHandle},

    transcript::Role,
};

const MAX_BYTES: usize = 16 * 1024 * 1024;
const MAX_PAGES: usize = 4096;

pub(super) struct Plan {
    parts: Parts,
    older: Option<Source>,
}

enum Source {
    Core {
        api: Api,
        session: PathBuf,
        cursor: AppTranscriptCursor,
    },
    Codex {
        handle: ThreadHandle,
        turn: String,
        anchor: Anchor,
        cursor: Option<String>,
        seen: HashSet<String>,
    },
}

struct Anchor {
    turn: String,
    item: String,
    role: Role,
    text: Arc<str>,
}

#[derive(Default)]
struct Parts {
    // Walk newest to oldest; reverse only once, when producing the clipboard.
    newest_first: Vec<Arc<str>>,
    bytes: usize,
}

impl Parts {
    fn length_with(&self, length: usize) -> Result<usize> {
        let separators = usize::from(!self.newest_first.is_empty()) * 2;
        let bytes = self
            .bytes
            .checked_add(length)
            .and_then(|n| n.checked_add(separators));
        ensure!(
            bytes.is_some_and(|n| n <= MAX_BYTES),
            "Текст хода превышает лимит копирования 16 МиБ"
        );
        Ok(bytes.unwrap())
    }

    fn push(&mut self, text: Arc<str>) -> Result<()> {
        if text.trim().is_empty() {
            return Ok(());
        }
        self.bytes = self.length_with(text.len())?;
        self.newest_first.push(text);
        Ok(())
    }

    fn push_owned(&mut self, text: String) -> Result<()> {
        if text.trim().is_empty() {
            return Ok(());
        }
        // Reject oversized source before allocating the shared text fragment.
        self.length_with(text.len())?;
        self.push(text.into())
    }

    fn finish(self) -> Result<String> {
        ensure!(
            !self.newest_first.is_empty(),
            "В этом ходе нет текста ответа для копирования"
        );
        let mut text = String::with_capacity(self.bytes);
        for part in self.newest_first.into_iter().rev() {
            if !text.is_empty() {
                text.push_str("\n\n");
            }
            text.push_str(&part);
        }
        Ok(text)
    }
}

impl Chat {
    pub(super) fn turn_copy_plan(&self, end_key: u64) -> Result<Plan> {
        let transcript = self.display_transcript();
        let entries = transcript.entries();
        let end = entries
            .iter()
            .position(|entry| entry.key == end_key)
            .ok_or_else(|| anyhow!("Этот ход больше не находится в открытой истории"))?;
        ensure!(
            entries[end].role != Role::User,
            "У этого сообщения ещё нет ответа"
        );
        let codex_turn = self
            .codex
            .as_ref()
            .map(|_| {
                transcript
                    .external_identity(end_key)
                    .map(|(turn, _)| turn.to_owned())
                    .ok_or_else(|| anyhow!("Не удалось определить ход Codex"))
            })
            .transpose()?;
        let mut parts = Parts::default();
        let mut complete = false;
        for entry in entries[..=end].iter().rev() {
            if entry.role == Role::User {
                complete = true;
                break;
            }
            if let Some(turn) = &codex_turn {
                let (row_turn, _) = transcript
                    .external_identity(entry.key)
                    .ok_or_else(|| anyhow!("Не удалось определить границу хода Codex"))?;
                if row_turn != turn {
                    complete = true;
                    break;
                }
            }
            ensure!(
                !entry.streaming,
                "Ответ ещё изменяется; дождитесь завершения хода"
            );
            if entry.role == Role::Assistant {
                parts.push(entry.text.clone())?;
            }
        }
        let older = if complete {
            None
        } else if let Some(binding) = &self.codex {
            let first = &entries[0];
            let (turn, item) = transcript
                .external_identity(first.key)
                .ok_or_else(|| anyhow!("Не удалось определить начало истории Codex"))?;
            // Archived windows trim whole pages, so this cursor still addresses
            // their oldest page. A moving live tail is resolved by opaque anchor.
            let cursor = binding.archive.as_ref().and_then(|_| {
                binding
                    .cursor_chain
                    .get(binding.oldest_page)
                    .cloned()
                    .flatten()
            });
            Some(Source::Codex {
                handle: binding.handle.clone(),
                turn: codex_turn.unwrap(),
                anchor: Anchor {
                    turn: turn.to_owned(),
                    item: item.to_owned(),
                    role: first.role,
                    text: first.text.clone(),
                },
                cursor,
                seen: entries[..=end]
                    .iter()
                    .filter_map(|entry| {
                        transcript
                            .external_identity(entry.key)
                            .map(|(_, item)| item.to_owned())
                    })
                    .collect(),
            })
        } else {
            self.history
                .copy_cursor(&self.session.transcript)
                .map(|cursor| -> Result<Source> {
                    Ok(Source::Core {
                        api: self
                            .api
                            .clone()
                            .ok_or_else(|| anyhow!("Сервер истории недоступен"))?,
                        session: self.session.dir.clone(),
                        cursor,
                    })
                })
                .transpose()?
        };
        Ok(Plan { parts, older })
    }
}
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
