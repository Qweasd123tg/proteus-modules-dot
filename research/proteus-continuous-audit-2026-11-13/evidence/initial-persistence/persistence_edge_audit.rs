//! Isolated audit probes. No network, modules or model are invoked.
use proteus_core::core::SessionStore;
use proteus_contracts::{domain::{new_session_id, new_thread_id}, model_standard::{CanonicalMessage, MessageRole}};

#[test]
fn metadata_partial_write_leaves_same_session_unretryable() {
    let config = tempfile::tempdir().unwrap();
    let workspace = tempfile::tempdir().unwrap();
    let session_id = new_session_id();
    let store = SessionStore::new(config.path(), workspace.path(), session_id).unwrap();
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    // Only this test process is limited, and the previous soft/hard limits are restored.
    let mut previous = libc::rlimit { rlim_cur: 0, rlim_max: 0 };
    unsafe { assert_eq!(libc::getrlimit(libc::RLIMIT_FSIZE, &mut previous), 0); }
    let handler = unsafe { libc::signal(libc::SIGXFSZ, libc::SIG_IGN) };
    let limited = libc::rlimit { rlim_cur: 64, rlim_max: previous.rlim_max };
    unsafe { assert_eq!(libc::setrlimit(libc::RLIMIT_FSIZE, &limited), 0); }
    let first = rt.block_on(store.append_history(new_thread_id(), None, &[CanonicalMessage::text(MessageRole::User, "first")])).unwrap_err();
    unsafe { assert_eq!(libc::setrlimit(libc::RLIMIT_FSIZE, &previous), 0); libc::signal(libc::SIGXFSZ, handler); }
    println!("first append: {first:#}");
    let metadata = std::fs::read(store.session_dir().join("session.json")).unwrap();
    println!("metadata length: {}; valid JSON: {}", metadata.len(), serde_json::from_slice::<serde_json::Value>(&metadata).is_ok());
    let retry = rt.block_on(store.append_history(new_thread_id(), None, &[CanonicalMessage::text(MessageRole::User, "retry")])).unwrap_err();
    println!("retry after limit restored: {retry:#}");
    let open = SessionStore::open(store.session_dir().to_path_buf()).unwrap_err();
    println!("reopen: {open:#}");
    assert_eq!(metadata.len(), 64);
    assert!(format!("{retry:#}").contains("failed to parse"));
    assert!(format!("{open:#}").contains("failed to parse"));
}

#[test]
fn valid_deep_workspace_exceeds_flat_session_component_limit() {
    let config = tempfile::tempdir().unwrap();
    let workspace = tempfile::tempdir().unwrap();
    let path = workspace.path().join("a".repeat(60)).join("b".repeat(60)).join("c".repeat(60)).join("d".repeat(60));
    std::fs::create_dir_all(&path).unwrap();
    let encoded = proteus_core::core::encode_workspace_path(&path).unwrap();
    println!("workspace path bytes: {}; encoded single component bytes: {}", path.as_os_str().len(), encoded.len());
    let store = SessionStore::new(config.path(), &path, new_session_id()).unwrap();
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let error = rt.block_on(store.append_history(new_thread_id(), None, &[CanonicalMessage::text(MessageRole::User, "deep workspace")])).unwrap_err();
    println!("first durable append: {error:#}");
    assert!(format!("{error:#}").contains("File name too long"));
}

#[test]
fn failed_blob_write_leaves_partial_temporary_after_successful_retry() {
    let config = tempfile::tempdir().unwrap();
    let workspace = tempfile::tempdir().unwrap();
    let store = SessionStore::new(config.path(), workspace.path(), new_session_id()).unwrap();
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let thread = new_thread_id();
    rt.block_on(store.append_history(thread, None, &[CanonicalMessage::text(MessageRole::User, "baseline")])).unwrap();
    let mut previous = libc::rlimit { rlim_cur: 0, rlim_max: 0 };
    unsafe { assert_eq!(libc::getrlimit(libc::RLIMIT_FSIZE, &mut previous), 0); }
    let handler = unsafe { libc::signal(libc::SIGXFSZ, libc::SIG_IGN) };
    let limited = libc::rlimit { rlim_cur: 65536, rlim_max: previous.rlim_max };
    unsafe { assert_eq!(libc::setrlimit(libc::RLIMIT_FSIZE, &limited), 0); }
    let large = CanonicalMessage::text(MessageRole::User, "x".repeat(300_000));
    let first = rt.block_on(store.append_history(thread, None, &[large.clone()])).unwrap_err();
    unsafe { assert_eq!(libc::setrlimit(libc::RLIMIT_FSIZE, &previous), 0); libc::signal(libc::SIGXFSZ, handler); }
    println!("blob failure: {first:#}");
    let leftovers: Vec<_> = std::fs::read_dir(store.session_dir().join("blobs")).unwrap().map(|entry| entry.unwrap().path()).collect();
    assert_eq!(leftovers.len(), 1);
    let partial = &leftovers[0];
    assert!(partial.file_name().unwrap().to_string_lossy().contains(".tmp."));
    assert_eq!(std::fs::metadata(partial).unwrap().len(), 65536);
    assert_eq!(store.load_messages().unwrap().len(), 1);
    rt.block_on(store.append_history(thread, None, &[large])).unwrap();
    println!("successful retry; partial temp still exists={}, bytes={}", partial.exists(), std::fs::metadata(partial).unwrap().len());
    assert!(partial.exists());
    assert_eq!(store.load_messages().unwrap().len(), 2);
}
