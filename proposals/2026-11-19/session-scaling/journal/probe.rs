
#[cfg(unix)]
#[tokio::test]
async fn measure_completed_journal_scaling() {
    use crate::{
        app_server::read_model::project_completed_transcript,
        model_standard::{CanonicalMessage, MessageRole},
    };
    use std::time::Instant;
    for prior in [0usize, 128, 512, 2048] {
        let (_state, server, _root) = test_state().await;
        server.start_session().await.unwrap();
        let store = server.runtime.session_store().unwrap();
        let thread = crate::domain::new_thread_id();
        store.clear_history(thread).await.unwrap();
        let seed = "some text / строка / 漢字 ".repeat(24);
        for i in 0..prior {
            let role = if i % 2 == 0 { MessageRole::User } else { MessageRole::Assistant };
            let row = CanonicalMessage::text(role, format!("{i:04} {seed}"));
            store.append_history(thread, None, &[row]).await.unwrap();
        }
        let old = project_completed_transcript(store).unwrap();
        assert!(old.cursor.is_some());
        let mut expected = old.messages.len();
        for rep in 0..5 {
            let marker = format!("projection-suffix-{rep}");
            let row = CanonicalMessage::text(MessageRole::Assistant, marker.clone());
            store.append_history(thread, None, &[row]).await.unwrap();
            eprintln!("MEASURE_START");
            let t = Instant::now();
            let completed = project_completed_transcript(store).unwrap();
            let ms = t.elapsed().as_secs_f64() * 1000.0;
            let actual = completed.cursor.unwrap().before + completed.messages.len();
            expected += 1;
            assert_eq!(actual, prior.max(50) - 50 + expected);
            assert_eq!(completed.messages.last().unwrap().text, marker);
            eprintln!("SETTLEMENT prior={prior} rep={rep} projected={actual} wall_ms={ms:.3}");
        }
    }
}
