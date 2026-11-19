"""Test-only lower-bound: omit disposable persistence, but keep verified render.
This is strictly NOT a runtime change or a deployable deferred-publish path."""
from pathlib import Path
import sys
root=Path(sys.argv[1])/'crates/proteus-core/src'
p=root/'core/session_store/remote/prepared.rs'
s=p.read_text()
needle='                self.store.save_read_model(&source, &model);'
assert s.count(needle)==1
s=s.replace(needle,'''                #[cfg(test)]
                if std::env::var_os("R13_READY_BOUND").is_some() {
                    let cut = model.transcript.len().saturating_sub(50);
                    let revision = source.revision().expect("validated source returns revision");
                    let view = SessionReadView {
                        summary: model.summary,
                        revision: model.conversation.revision,
                        usage: model.usage,
                        transcript: model.transcript.into_iter().skip(cut).collect(),
                        cursor: Some(proteus_contracts::app_protocol::AppTranscriptCursor {
                            revision,
                            before: cut,
                            base: None,
                        }),
                    };
                    return Ok((self.store, view, None));
                }
'''+needle)
p.write_text(s)
p=root/'app_server/http/tests/session_reads.rs'
s=p.read_text()
needle='        let start = Instant::now();\n        server.send_user_message("hello".to_owned()).await.unwrap();'
assert s.count(needle)==1
s=s.replace(needle,'''        if std::env::var_os("R13_READY_BOUND").is_some() {
            assert_eq!(recent.messages.len(), 50);
            for (display, canonical) in recent.messages.iter().zip(&messages[rows-50..]) {
                assert_eq!(display.message_id, Some(canonical.id));
                assert_eq!(display.text, canonical.display_text());
                assert!(display.timestamp_ms.is_some());
            }
            assert_eq!(std::fs::read(&journal).unwrap(), prior);
            eprintln!("R13_BOUND rows={rows} tail=50 cache_publish=omitted");
            server.shutdown().await;
            continue;
        }
'''+needle)
p.write_text(s)
