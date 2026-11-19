
#[cfg(unix)]
#[tokio::test]
async fn perf7_real_turn_fixed_active_history() {
    use crate::{
        core::{PreparedSession, SessionStore},
        domain::{HistoryCompactionReport, new_session_id, new_thread_id},
        model_standard::{CanonicalMessage, MessageRole},
    };
    use proteus_contracts::storage::journal::JournalEntry;
    use std::time::Instant;
    let cases = std::env::var("PERF7_CASES").unwrap_or_else(|_| "100,2000,5000".to_owned());
    for case in cases.split(',') {
        let rows: usize = case.parse().unwrap();
        const ACTIVE: usize = 100;
        let root = tempfile::tempdir().unwrap();
        let cwd = root.path();
        let config_path = cwd.join("config.toml");
        let storage = crate::test_support::storage(cwd);
        let store = SessionStore::new(storage.clone(), cwd, cwd, new_session_id()).unwrap();
        let thread = new_thread_id();
        let messages: Vec<_> = (0..rows)
            .map(|i| {
                let label = if i >= rows - ACTIVE { format!("active-{:04}", i - (rows - ACTIVE)) } else { format!("archive-{i:04}") };
                CanonicalMessage::text(
                    if i % 2 == 0 { MessageRole::User } else { MessageRole::Assistant },
                    format!("{label}: {}", "Фиктивная строка журнала. ".repeat(3)),
                )
            })
            .collect();
        for chunk in messages.chunks(100) {
            store.append_history(thread, None, chunk).await.unwrap();
        }
        if rows > ACTIVE {
            let mut report = HistoryCompactionReport::unchanged(rows, Some("Synthetic tail compaction".into()));
            report.changed = true;
            report.output_messages = ACTIVE;
            report.summary_source = Some("history-scale-fixture-tail".into());
            store.replace_history(thread, None, &messages[rows - ACTIVE..], Some(report))
                .await.unwrap();
        }
        let session_dir = store.session_dir().to_path_buf();
        let journal = session_dir.join("journal.jsonl");
        let prior = std::fs::read(&journal).unwrap();
        let bytes = prior.len();
        let prepared = PreparedSession::from_dir(storage.clone(), session_dir.clone()).unwrap();
        drop(store);
        let server = AgentAppServer::launch_inner(dogfood_loop_config(), cwd.to_path_buf(),
            Some(&config_path), Some(dogfood_loop_catalog()), Some(prepared), None, Some(storage))
            .await.unwrap();
        let running_store = server.runtime.session_store().unwrap();
        assert_eq!(running_store.load_messages().unwrap().len(), ACTIVE);
        let recent = server.events.completed_history().unwrap();
        assert_eq!(recent.cursor.as_ref().unwrap().before + recent.messages.len(), rows);
        eprintln!("CASE display={rows} active={ACTIVE} journal_bytes={bytes}");
        let start = Instant::now();
        server.send_user_message("hello".to_owned()).await.unwrap();
        let elapsed = start.elapsed().as_secs_f64() * 1_000.0;
        let records = running_store.load_records().unwrap();
        let reqs: Vec<_> = records.iter().filter_map(|entry| match &entry.entry {
            JournalEntry::ModelRequestRecorded(row) => Some(&row.request),
            _ => None,
        }).collect();
        let counts: Vec<_> = reqs.iter().map(|r| r.messages.len()).collect();
        assert!(!counts.is_empty());
        // Old archive content must never enter the active request.
        assert!(reqs.iter().all(|r| !serde_json::to_string(&r.messages).unwrap().contains("archive-")));
        assert!(std::fs::read(&journal).unwrap().starts_with(&prior));
        let now = server.events.completed_history().unwrap();
        eprintln!("TURN display={rows} active={ACTIVE} request_messages={counts:?} total_ms={elapsed:.3} projected={} journal_bytes_after={}", now.cursor.as_ref().unwrap().before + now.messages.len(), std::fs::metadata(&journal).unwrap().len());
        assert!(now.messages.iter().any(|msg| msg.role == "assistant"));
        assert_eq!(now.cursor.as_ref().unwrap().before + now.messages.len(), rows + 2);
        server.shutdown().await;
    }
}
