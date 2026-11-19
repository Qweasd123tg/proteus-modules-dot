#![allow(dead_code, unused_imports)]
pub use proteus_contracts::{contracts, domain, model_standard};
mod app_server {
    pub mod transcript;
}
mod core {
    pub use proteus_contracts::storage::journal::*;
    pub use proteus_session_semantics::{JournalProjection, history_message_sha256};
    mod prefix;
    pub(crate) use prefix::PrefixIdentities;
    pub struct JournalReadSnapshot;
    pub struct JournalReadCursor;
    pub struct DisplayRecords;
    #[derive(Debug)]
    pub struct SessionTranscriptAppend {
        pub transcript: Vec<proteus_contracts::app_protocol::AppTranscriptMessage>,
        pub conversation_appended: usize,
    }
    pub fn is_display_kind(k: JournalKind) -> bool {
        k.is_display_record()
    }
    impl JournalReadCursor {
        pub fn last_session_seq(&self) -> u64 {
            panic!("unexpected storage cursor")
        }
    }
    impl JournalReadSnapshot {
        pub fn scan_display(
            &mut self,
            _: impl FnMut(JournalRecord) -> anyhow::Result<()>,
        ) -> anyhow::Result<()> {
            panic!("unexpected storage scan")
        }
        pub fn scan_selected_after(
            &mut self,
            _: &JournalReadCursor,
            _: fn(JournalKind) -> bool,
            _: impl FnMut(JournalRecord) -> anyhow::Result<()>,
        ) -> anyhow::Result<bool> {
            panic!("unexpected storage scan")
        }
    }
    impl DisplayRecords {
        pub fn scan(
            &mut self,
            _: impl FnMut(JournalRecord) -> anyhow::Result<()>,
        ) -> anyhow::Result<()> {
            panic!("unexpected storage scan")
        }
    }
}
