"""Add test-only current Core timings; leave all production decisions unchanged."""
from pathlib import Path
import sys
base=Path(sys.argv[1])
rust=base/'crates/proteus-core/src'
def sub(f,a,b):
 p=rust/f; s=p.read_text(); assert s.count(a)==1,(p,a); p.write_text(s.replace(a,b))
sub('app_server/runs.rs','            let history = completed_transcript_from_commit(server.runtime.clone(), display).await;', '''            eprintln!("SETTLE_BEGIN commit_supplied={}", display.is_some());
            let measured = std::time::Instant::now();
            let history = completed_transcript_from_commit(server.runtime.clone(), display).await;
            eprintln!("SETTLE_END wall_ms={:.3} ok={}", measured.elapsed().as_secs_f64() * 1000., history.is_ok());''')
sub('app_server/read_model.rs','        release_projection_memory();\n        return Ok(CompletedTranscript {','        eprintln!("COMMIT_PROJECTION used=true");\n        release_projection_memory();\n        return Ok(CompletedTranscript {')
sub('app_server/read_model.rs','    project_completed_transcript(store)\n','    eprintln!("COMMIT_PROJECTION used=false");\n    project_completed_transcript(store)\n')
snap='core/session_store/remote/snapshot.rs'
sub(snap, '        loop {\n            let cursor_before_page = after_seq;', '''        let from = after_seq;
        let mut pages = 0;
        let mut received = 0;
        loop {
            pages += 1;
            let cursor_before_page = after_seq;''')
sub(snap, '            for record in page.records {','            received += page.records.len();\n            for record in page.records {')
sub(snap,'                    return Ok(());','                    eprintln!("SCAN display_only={} from={from} received={received} pages={pages}", self.display_only);\n                    return Ok(());')
with (rust/'app_server/http/tests/session_reads.rs').open('a') as f:f.write((Path(__file__).resolve().parent/'probe.rs').read_text())
