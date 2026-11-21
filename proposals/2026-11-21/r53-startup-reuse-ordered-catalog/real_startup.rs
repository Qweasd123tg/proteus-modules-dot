use super::*;
use crate::model_standard::{CanonicalMessage, MessageRole};
use std::{
    fs::FileTimes,
    time::{Duration, UNIX_EPOCH},
};

#[tokio::test]
async fn prepared_startup_orders_a_real_large_provider_catalog() {
    let root = tempfile::tempdir().unwrap();
    let workspace = root.path().join("synthetic-workspace");
    std::fs::create_dir(&workspace).unwrap();
    let service = crate::test_support::storage(&workspace);
    let mut journals = Vec::new();
    let mut expected = None;
    // The corrupt newest root must be rejected by the existing strict path,
    // and must not affect the next valid root chosen from the ranked catalog.
    for i in 0..40 {
        let store = RemoteSessionStore::new(
            service.clone(),
            root.path(),
            &workspace,
            crate::domain::new_session_id(),
        )
        .unwrap();
        let journal = store.journal_path();
        if i == 38 {
            expected = Some(store.session_dir().to_path_buf());
        }
        store
            .append_history(
                crate::domain::new_thread_id(),
                None,
                &[CanonicalMessage::text(
                    MessageRole::User,
                    format!("synthetic root {i}"),
                )],
            )
            .await
            .unwrap();
        drop(store);
        if i == 39 {
            // Deliberate malformed fixture, not an exploit or an actual chat.
            std::fs::write(&journal, b"not-json\n").unwrap();
        }
        std::fs::File::options()
            .write(true)
            .open(&journal)
            .unwrap()
            .set_times(
                FileTimes::new().set_modified(UNIX_EPOCH + Duration::from_secs(1_700_000_000 + i)),
            )
            .unwrap();
        let original = std::fs::read(&journal).unwrap();
        journals.push((journal, original));
    }
    let catalog = catalog::candidates(service.clone(), root.path(), Some(&workspace)).unwrap();
    assert_eq!(catalog.len(), 40);
    assert!(
        catalog
            .windows(2)
            .all(|p| p[0].updated_at_ms > p[1].updated_at_ms)
    );
    let before = catalog[0].local_path.clone();
    assert_ne!(before, expected);
    let opened = prepare_latest_workspace_session(service, root.path(), &workspace)
        .unwrap()
        .unwrap();
    assert_eq!(opened.session_dir(), expected.unwrap());
    assert_eq!(opened.message_count(), 1);
    for (journal, original) in journals {
        assert_eq!(std::fs::read(&journal).unwrap(), original);
    }
}
