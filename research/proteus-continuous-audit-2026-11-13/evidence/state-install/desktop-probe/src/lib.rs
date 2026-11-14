#![allow(dead_code)]
pub mod settings {
    #[path = "/workspace/shared/state-install-trace/src/settings/mcp.rs"]
    pub mod mcp;
    #[path = "/workspace/shared/state-install-trace/src/settings/draft.rs"]
    pub mod draft;
    #[path = "/workspace/shared/state-install-trace/src/settings/addons.rs"]
    pub mod addons;
}
#[cfg(test)]
mod tests {
    use super::settings::draft::Draft;
    use proteus_contracts::app_protocol::config_builder::{ConfigBuilderSnapshot, ConfigBuilderState};

    #[test]
    fn history_restore_none_provider_generates_no_change() {
        let snapshot = ConfigBuilderSnapshot {
            active_provider: Some("provider-a".into()),
            permission_mode: "normal".into(),
            ..ConfigBuilderSnapshot::default()
        };
        let old = ConfigBuilderState {
            active_provider: None,
            permission_mode: "normal".into(),
            ..ConfigBuilderState::default()
        };
        let baseline = Draft::from_snapshot(&snapshot);
        let restored = Draft::from_revision(&snapshot, &old);
        assert_eq!(restored.provider, None);
        assert_ne!(restored, baseline);
        assert!(!restored.is_dirty(&baseline));
        assert!(restored.changes(&baseline).active_provider.is_none());
        eprintln!("baseline.provider={:?}, restored.provider={:?}, dirty={}, request={}",
            baseline.provider, restored.provider, restored.is_dirty(&baseline),
            serde_json::to_string(&restored.changes(&baseline)).unwrap());
    }
}
