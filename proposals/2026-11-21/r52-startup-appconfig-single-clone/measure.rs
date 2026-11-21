//! Temporarily included from the actual AppServer startup module.
use super::*;
use crate::model_standard::{CanonicalMessage, MessageRole};

pub(in crate::app_server) fn copy_config(config: &AppConfig, site: &str) -> AppConfig {
    let (owned, cost) = crate::r52_test_alloc::measure(|| std::hint::black_box(config.clone()));
    println!(
        "r52 config {} site={} calls={} bytes={}",
        config.profile.name, site, cost.calls, cost.bytes
    );
    owned
}

#[tokio::test]
async fn launch_profile_copy_probe() {
    for (name, count, len) in [
        ("default", 0, 0),
        ("commands", 32, 128),
        ("long", 4, 65536),
        ("stress", 32, 65536),
    ] {
        let root = tempfile::tempdir().unwrap();
        let cwd = root.path().join("project");
        let donor = root.path().join("other-project");
        std::fs::create_dir_all(&cwd).unwrap();
        std::fs::create_dir_all(&donor).unwrap();
        let path = root.path().join("fixture.toml");
        let mut config = crate::test_model::config();
        for i in 0..count {
            config.commands.insert(
                format!("fixture{i}"),
                serde_json::from_value(serde_json::json!({
                    "description":"Synthetic prompt snippet (no invocation)",
                    "prompt":"x".repeat(len),
                }))
                .unwrap(),
            );
        }
        for mode in ["fresh", "preferred"] {
            config.profile.name = format!("{name}_{mode}");
            let canonical_before = serde_json::to_value(&config).unwrap();
            let saved = if mode == "preferred" {
                let store = crate::core::SessionStore::new(
                    crate::test_support::storage(&donor),
                    root.path(),
                    &donor,
                    crate::domain::new_session_id(),
                )
                .unwrap();
                store
                    .append_history(
                        crate::domain::new_thread_id(),
                        None,
                        &[CanonicalMessage::text(
                            MessageRole::User,
                            "r52 synthetic saved history",
                        )],
                    )
                    .await
                    .unwrap();
                let bytes = std::fs::read(store.journal_path()).unwrap();
                let dir = store.session_dir().to_owned();
                let journal = store.journal_path();
                drop(store);
                Some((dir, journal, bytes))
            } else {
                None
            };
            let (handle, default_workspace) = launch_http_selected(
                config.clone(),
                cwd.clone(),
                Some(&path),
                None,
                mode == "fresh",
                saved.as_ref().map(|s| s.0.clone()),
            )
            .await
            .unwrap();
            assert_eq!(
                serde_json::to_value(&*handle.config.read().await).unwrap(),
                canonical_before
            );
            assert_eq!(default_workspace, cwd);
            assert_eq!(
                handle
                    .command_catalog()
                    .await
                    .unwrap()
                    .iter()
                    .filter(|cmd| cmd.name.starts_with("fixture"))
                    .count(),
                count
            );
            if let Some((dir, journal, bytes)) = &saved {
                assert_eq!(handle.session_dir_path().as_ref(), Some(dir));
                assert_eq!(handle.cwd_path(), donor);
                let history = handle.transcript().await.unwrap();
                assert_eq!(history.len(), 1);
                assert_eq!(history[0].text, "r52 synthetic saved history");
                assert_eq!(std::fs::read(journal).unwrap(), *bytes);
            } else {
                assert_eq!(handle.cwd_path(), cwd);
                assert!(handle.transcript().await.unwrap().is_empty());
            }
            handle.shutdown().await;
        }
    }
}
