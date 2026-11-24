// Text-only HistoryMutated adapter; nonempty unrelated fields are not fixtures.
use serde_json::Value;
type HistoryCompactionReport = Value;
pub(crate) mod contracts {
    pub type WorkflowToolResultBinding = serde_json::Value;
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
#[non_exhaustive]
pub enum ContentPart {
    Text { text: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(
    tag = "kind",
    content = "payload",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum JournalEntry {
    HistoryMutated(HistoryMutated),
}

impl JournalEntry {
    pub fn kind(&self) -> JournalKind {
        JournalKind::HistoryMutated
    }
    pub fn stored_payload_value(&self) -> serde_json::Result<Value> {
        self.payload_value()
    }
    pub fn from_stored_kind_and_payload(
        kind: JournalKind,
        value: Value,
    ) -> serde_json::Result<Self> {
        assert!(matches!(kind, JournalKind::HistoryMutated));
        serde_json::from_value(value).map(Self::HistoryMutated)
    }
    pub fn from_stored_kind_and_bytes(kind: JournalKind, bytes: &[u8]) -> serde_json::Result<Self> {
        assert!(matches!(kind, JournalKind::HistoryMutated));
        serde_json::from_slice(bytes).map(Self::HistoryMutated)
    }
}
