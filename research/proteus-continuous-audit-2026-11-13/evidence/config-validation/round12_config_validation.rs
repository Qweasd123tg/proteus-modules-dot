//! Diagnostic tests: assert the observed malformed-save behavior, not a fix.
use super::*;

fn fixture_config() -> AppConfig {
    let mut config = AppConfig::default();
    config.active_provider = None;
    config.providers.clear();
    config.agent_control.surface = crate::core::AgentControlSurface::None;
    config.tools.enabled = vec!["probe_command".into()];
    let fixture = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/process_commands.py");
    config.components.insert(
        "audit-probe".into(),
        serde_json::from_value(serde_json::json!({
            "command": "python3", "args": [fixture],
            "exports": {"tool": {"probe.commands": {}}}
        }))
        .unwrap(),
    );
    config
}

async fn launch(extension: &str) -> (tempfile::TempDir, PathBuf, AppServerHandle) {
    let root = tempfile::tempdir().unwrap();
    let source = root.path().join(format!("config.{extension}"));
    let config = fixture_config();
    let bytes = if extension == "json" {
        serde_json::to_vec_pretty(&config).unwrap()
    } else {
        toml::to_string_pretty(&config).unwrap().into_bytes()
    };
    std::fs::write(&source, bytes).unwrap();
    let loaded = AppConfig::load(Some(&source)).await.unwrap();
    let server = AgentAppServer::launch(loaded, root.path().into(), Some(&source))
        .await
        .unwrap();
    (root, source, server)
}

#[tokio::test]
async fn audit_round12_save_unknown_module_config_slot_bricks_subsequent_save_and_cold_load() {
    for extension in ["toml", "json"] {
        let (_root, source, server) = launch(extension).await;
        let slot = "unknown_slot";
        let mutation = BTreeMap::from([(
            slot.to_string(),
            BTreeMap::from([("unselected".to_string(), serde_json::json!({"audit": 1}))]),
        )]);
        let response = server
            .set_config_builder(BTreeMap::new(), None, mutation, None, None, None)
            .await
            .expect("Save unexpectedly accepts unknown module_config slot");
        assert!(response.module_config.contains_key(slot));
        assert!(server.config.read().await.module_config.contains_key(slot));
        let error = AppConfig::load(Some(&source)).await.unwrap_err();
        assert!(format!("{error:#}").contains("unknown module_config slot"));
        let retry = server
            .set_config_builder(
                BTreeMap::new(),
                None,
                BTreeMap::from([(slot.to_string(), BTreeMap::new())]),
                None,
                None,
                Some(PermissionMode::Plan),
            )
            .await
            .unwrap_err();
        assert!(format!("{retry:#}").contains("unknown module_config slot"));
        tokio::time::sleep(std::time::Duration::from_millis(600)).await;
        let watch_error = server.addons_snapshot().await.reload_error;
        assert!(
            watch_error
                .as_deref()
                .is_some_and(|e| e.contains("unknown module_config slot"))
        );
        eprintln!(
            "ROUND12 ({extension}): save=OK; ACK/live contain unknown_slot; cold load={error:#}; attempted correction={retry:#}; watcher={watch_error:?}"
        );
        server.shutdown().await;
    }
}

#[tokio::test]
async fn audit_round12_control_supported_slot_save_roundtrips() {
    for extension in ["toml", "json"] {
        let (_root, source, server) = launch(extension).await;
        let mutation = BTreeMap::from([(
            "tool".to_string(),
            BTreeMap::from([("unselected".to_string(), serde_json::json!({"audit": 1}))]),
        )]);
        server
            .set_config_builder(BTreeMap::new(), None, mutation, None, None, None)
            .await
            .unwrap();
        let cold = AppConfig::load(Some(&source)).await.unwrap();
        assert_eq!(cold.module_config["tool"]["unselected"]["audit"], 1);
        server
            .set_config_builder(
                BTreeMap::new(),
                None,
                BTreeMap::new(),
                None,
                None,
                Some(PermissionMode::Plan),
            )
            .await
            .unwrap();
        eprintln!(
            "ROUND12 CONTROL ({extension}): supported slot save, cold load and follow-up Save all succeed"
        );
        server.shutdown().await;
    }
}
