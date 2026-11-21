use std::time::Duration;

use super::*;
use crate::app_server::AgentAppServer;
use crate::app_server::http::config::HttpServerConfig;
use crate::model_standard::{CanonicalMessage, MessageRole};

include!("r58_stock_watcher.rs");

async fn create(
    root: &Path,
    persist: bool,
    old: Option<crate::core::StorageService>,
) -> AppServerHandle {
    let config = root.join("synthetic.toml");
    let server = AgentAppServer::launch_with_storage(
        crate::test_model::config(),
        root.to_path_buf(),
        Some(&config),
        old,
    )
    .await
    .unwrap();
    if persist {
        server
            .runtime
            .session_store()
            .unwrap()
            .append_history(
                crate::domain::new_thread_id(),
                None,
                &[CanonicalMessage::text(
                    MessageRole::User,
                    "synthetic saved chat",
                )],
            )
            .await
            .unwrap();
    }
    server
}

fn reset_count() {
    R58_KEY_OBSERVATIONS.with(|count| count.set(0));
}

fn count() -> usize {
    R58_KEY_OBSERVATIONS.with(|count| count.get())
}

fn security() -> HttpSecurity {
    HttpSecurity::from_config(&HttpServerConfig::default())
}

fn observed_activity(event: AppServerEvent) -> PathBuf {
    let AppServerEvent::SessionActivityUpdated { session_dir, .. } = event else {
        panic!("expected activity event")
    };
    session_dir
}

async fn next_activity(rx: &mut broadcast::Receiver<AppServerEvent>) -> PathBuf {
    observed_activity(
        tokio::time::timeout(Duration::from_secs(3), rx.recv())
            .await
            .expect("activity watcher delivered event")
            .unwrap(),
    )
}

async fn compare_storage(root: &Path, stock: bool, persist: bool) -> (usize, usize) {
    let one = create(root, persist, None).await;
    let two = create(root, persist, one.storage.clone()).await;
    let key_one = session_key(one.session_dir_path().unwrap());
    let key_two = session_key(two.session_dir_path().unwrap());
    let (stop, _) = broadcast::channel(1);
    reset_count();
    let state = if stock {
        HttpAppState::stock_new_for_workspace(one.clone(), root.to_path_buf(), stop, security())
            .await
    } else {
        HttpAppState::new_for_workspace(one.clone(), root.to_path_buf(), stop, security()).await
    };
    let initial = count();
    assert_eq!(state.launch.initial_session_dir, one.session_dir_path());
    reset_count();
    let mut events = state.subscribe_activity();
    if stock {
        state.stock_remember_server(two.clone()).await;
    } else {
        state.remember_server(two.clone()).await;
    }
    let remembered = count();
    assert_eq!(next_activity(&mut events).await, key_two);
    assert!(state.server_for_session_dir(&key_one).await.is_some());
    assert!(state.server_for_session_dir(&key_two).await.is_some());
    assert_eq!(
        *state.watched_sessions.lock().unwrap(),
        HashSet::from([key_one.clone(), key_two.clone()])
    );
    for (server, key) in [(&one, &key_one), (&two, &key_two)] {
        server
            .events
            .send(AppServerEvent::Error {
                message: "synthetic activity".into(),
            })
            .unwrap();
        assert_eq!(&next_activity(&mut events).await, key);
    }
    one.shutdown().await;
    two.shutdown().await;
    (initial, remembered)
}

#[tokio::test(flavor = "current_thread")]
async fn r58_watcher_resolves_once_at_registration_and_keeps_activity() {
    for persisted in [false, true] {
        let old = tempfile::tempdir().unwrap();
        let new = tempfile::tempdir().unwrap();
        let first = compare_storage(old.path(), true, persisted).await;
        let second = compare_storage(new.path(), false, persisted).await;
        assert_eq!(first, (2, 4));
        assert_eq!(second, (1, 3));
        println!(
            "persisted={persisted} initial key resolutions {}→{}; remember incl. activity {}→{}",
            first.0, second.0, first.1, second.1
        );
    }
}

#[cfg(unix)]
#[tokio::test(flavor = "current_thread")]
async fn r58_watcher_follows_registered_key_after_alias_retarget_and_retirement() {
    use std::os::unix::fs::symlink;
    for stock in [true, false] {
        let root = tempfile::tempdir().unwrap();
        let one = create(root.path(), true, None).await;
        let two = create(root.path(), true, one.storage.clone()).await;
        let dir_one = one.session_dir_path().unwrap();
        let dir_two = two.session_dir_path().unwrap();
        let (stop, _) = broadcast::channel(1);
        let state = if stock {
            HttpAppState::stock_new_for_workspace(
                one.clone(),
                root.path().to_path_buf(),
                stop,
                security(),
            )
            .await
        } else {
            HttpAppState::new_for_workspace(
                one.clone(),
                root.path().to_path_buf(),
                stop,
                security(),
            )
            .await
        };
        if stock {
            state.stock_remember_server(two.clone()).await;
        } else {
            state.remember_server(two.clone()).await;
        }
        let alias = root.path().join("alias");
        symlink(&dir_one, &alias).unwrap();
        assert_eq!(
            state
                .resolve_session_dir(alias.join("journal.jsonl"))
                .await
                .unwrap(),
            dir_one
        );
        assert_eq!(
            state
                .server_for_session_dir(&alias)
                .await
                .unwrap()
                .session_id(),
            one.session_id()
        );

        // Shutdown first just as the ownership route does. Remove via the alias,
        // then atomically retarget it to the still-live second registration.
        one.shutdown().await;
        assert_eq!(
            state
                .remove_session_server(&alias)
                .await
                .unwrap()
                .session_id(),
            one.session_id()
        );
        let alias_next = root.path().join("alias-next");
        symlink(&dir_two, &alias_next).unwrap();
        std::fs::rename(&alias_next, &alias).unwrap();
        assert_eq!(
            state
                .server_for_session_dir(&alias)
                .await
                .unwrap()
                .session_id(),
            two.session_id()
        );
        assert_eq!(
            *state.watched_sessions.lock().unwrap(),
            HashSet::from([dir_two.clone()])
        );
        assert!(state.server_for_session_dir(&dir_one).await.is_none());
        let mut events = state.subscribe_activity();
        two.events
            .send(AppServerEvent::Error {
                message: "synthetic surviving activity".into(),
            })
            .unwrap();
        assert_eq!(next_activity(&mut events).await, dir_two);
        two.shutdown().await;
    }
}
