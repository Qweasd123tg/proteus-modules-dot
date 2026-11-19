"""Extend an R11-instrumented COPY, before the libtest build. No changes to production."""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "crates/proteus-core/src/app_server/http/tests/session_reads.rs"
s = p.read_text()
if "async fn r9_real_turn_fixed_active_history" not in s or "async fn r12_get" in s:
    raise SystemExit("expected a fresh R11-instrumented copy")
anchor = '        eprintln!("CASE display={rows}'
i = s.index(anchor)
s = s[:i] + '''        let pack_smoke = if std::env::var_os("R12_PACK_SMOKE").is_some() {
            assert!(fresh, "R12 controls need a fresh storage client for prepare");
            assert!(rows >= 851, "use at least two packed groups plus a hot tail");
            let (shutdown, _) = broadcast::channel(1);
            let state = HttpAppState::new(server.clone(), shutdown, test_security()).await;
            let query = format!("session_dir={}", session_dir.display());
            let rev = recent.cursor.as_ref().unwrap().revision.clone();
            let (_, exported) = r12_export(&state, &query).await;
            assert_eq!(exported.len(), rows);
            for (i, (row, msg)) in exported.iter().zip(&messages).enumerate() {
                assert_eq!(row["text"], msg.display_text(), "text {i}");
                assert_eq!(row["role"], if i % 2 == 0 { "user" } else { "assistant" });
                assert_eq!(row["message_id"], serde_json::to_value(msg.id).unwrap(), "id {i}");
                assert!(row["timestamp_ms"].is_i64(), "no journal timestamp at {i}");
            }
            assert_eq!(serde_json::to_value(&recent.messages).unwrap().as_array().unwrap(),
                       &exported[rows-50..]);
            r12_scroll(&state, &query, &rev, &exported).await;
            assert_eq!(std::fs::read(&journal).unwrap(), prior);
            Some((state, query, rev, exported))
        } else { None };
''' + s[i:]
anchor = '        server.shutdown().await;'
i = s.index(anchor, i)
s = s[:i] + '''        if let Some((mut state, query, previous, before)) = pack_smoke {
            let rev = &now.cursor.as_ref().unwrap().revision;
            assert_ne!(rev, &previous, "append must create a revision");
            let (raw, exported) = r12_export(&state, &query).await;
            assert_eq!(exported.len(), rows + 2);
            assert_eq!(&exported[..rows], &before);
            assert_eq!(exported[rows]["text"], "hello");
            assert_eq!(exported[rows+1]["role"], "assistant");
            assert_eq!(serde_json::to_value(&now.messages).unwrap().as_array().unwrap(),
                       &exported[rows+2-50..]);
            let base = now.cursor.as_ref().unwrap().base.as_ref().expect("append prefix");
            assert_eq!(base.revision, previous);
            assert_eq!(base.common_prefix, rows);
            r12_page(&state, &query, &previous, rows, &before).await;
            r12_page(&state, &query, &previous, 401, &before).await;
            let after = std::fs::read(&journal).unwrap();
            assert!(after.len() > prior.len() && after.starts_with(&prior));
            server.shutdown().await;
            assert!(state.remove_session_server(&session_dir).await.is_some());
            // The test-support factory reuses services per cwd. A NEW cwd gives
            // an independent worker; no active handle/resume or warm worker fast path.
            let worker_cwd = tempfile::tempdir().unwrap();
            let next = crate::test_support::storage(worker_cwd.path());
            assert!(!std::sync::Arc::ptr_eq(&next, state.storage.as_ref().unwrap()));
            state.storage = Some(next);
            assert!(state.server_for_session_dir(&session_dir).await.is_none());
            r12_scroll(&state, &query, rev, &exported).await;
            let (cold_raw, _) = r12_export(&state, &query).await;
            assert!(raw == cold_raw, "offline /history must be byte-identical");
            let invalid = format!("/history/page?{query}&before=1&revision={}", "0".repeat(64));
            r12_get(&state, &invalid, StatusCode::BAD_REQUEST).await;
            let outside = format!("/history/page?{query}&before={}&revision={rev}", rows+3);
            r12_get(&state, &outside, StatusCode::BAD_REQUEST).await;
            assert!(state.server_for_session_dir(&session_dir).await.is_none());
            assert_eq!(std::fs::read(&journal).unwrap(), after);
            eprintln!("R12_SMOKE rows={rows} after={} offline_worker=fresh export=byte-identical history_prefix=unchanged retained_revision=verified", exported.len());
        } else { server.shutdown().await; }
''' + s[i+len(anchor):]
s += '\n' + Path(__file__).with_name("controls.rs").read_text()
p.write_text(s)
