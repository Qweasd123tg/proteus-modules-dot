use domain::{
    Event, EventContext, EventEnvelope, ModelRef, SessionId, TokenUsageCategory,
    TokenUsageSnapshot, TokenUsageSource, new_session_id, new_thread_id, new_turn_id,
};
use model_standard::TokenUsage;
pub(crate) use proteus_contracts::{domain, model_standard};
use std::{
    fs::File,
    io::{BufWriter, Write},
    path::Path,
};
mod heap;
mod app_server {
    pub(crate) use proteus_contracts::app_protocol::*;
    include!("path_utils.rs");
}
mod core {
    mod context_summary;
    pub(crate) use context_summary::summarize_context_history;
}
macro_rules! version {
    ($v:ident) => {
        mod $v {
            use crate::{app_server::*, *};
            mod context_map;
            pub(super) fn snapshot(
                path: &Path,
                id: Option<SessionId>,
            ) -> anyhow::Result<AppContextMapSnapshot> {
                context_map::build_context_map_snapshot(context_map::ContextMapInput {
                    session_dir: Some(path.parent().unwrap().into()),
                    session_id: id,
                    workspace_path: None,
                    activity: None,
                    history: Vec::new(),
                    event_log_path: path.to_owned(),
                    diagnostics: vec!["caller".into()],
                })
            }
        }
    };
}
version!(baseline);
version!(candidate);

fn usage(id: SessionId, seq: u64, cats: usize) -> EventEnvelope {
    let labels = [
        TokenUsageSource::Estimated,
        TokenUsageSource::Mixed,
        TokenUsageSource::Provider,
    ];
    let mut usage = TokenUsageSnapshot::new(
        ModelRef::new("provider", format!("model-{seq}")),
        seq as u32,
        (0..cats)
            .map(|i| {
                TokenUsageCategory::new(format!("cat-{i}"), i as u32 + seq as u32)
                    .with_source(labels[(i + seq as usize) % 3])
            })
            .collect(),
    )
    .with_source(labels[seq as usize % 3]);
    if seq % 2 == 0 {
        usage = usage
            .with_phase("x")
            .with_max_input_tokens(Some(3000))
            .with_compaction_trigger_tokens(Some(2200))
            .with_actual(Some(
                TokenUsage::new(678, 90).with_cached_input_tokens(Some(20)),
            ));
    }
    let mut event = EventEnvelope::new(
        EventContext::new(id, new_thread_id(), Some(new_turn_id())),
        seq,
        Event::TokenUsageUpdated { usage },
    );
    event.timestamp_ms = seq as i64;
    event
}

#[test]
fn allocation_traffic_in_complete_cold_context() {
    let d = tempfile::tempdir().unwrap();
    let id = new_session_id();
    for (n, cats) in [(0, 4), (1, 4), (128, 0), (128, 4), (1024, 4), (1024, 12)] {
        let p = d.path().join(format!("{n}-{cats}"));
        let mut log = BufWriter::new(File::create(&p).unwrap());
        for i in 0..n {
            serde_json::to_writer(&mut log, &usage(id, i, cats)).unwrap();
            writeln!(log).unwrap();
        }
        drop(log);
        let (a, before) = heap::measure(|| baseline::snapshot(&p, Some(id)).unwrap());
        let (b, after) = heap::measure(|| candidate::snapshot(&p, Some(id)).unwrap());
        assert_eq!(
            serde_json::to_vec(&a).unwrap(),
            serde_json::to_vec(&b).unwrap()
        );
        assert_eq!(
            b.latest_usage.as_ref().map(|u| u.timestamp_ms.unwrap()),
            n.checked_sub(1).map(|v| v as i64)
        );
        println!(
            "samples={n} categories={cats} calls={}->{} bytes={}->{}",
            before.calls, after.calls, before.bytes, after.bytes
        );
        if n > 1 {
            assert!(before.calls - after.calls >= (n - 1) as usize * (cats + 1));
        } else {
            assert_eq!((before.bytes, before.calls), (after.bytes, after.calls));
        }
        #[cfg(unix)]
        {
            let (_, a) = heap::measure(|| baseline::snapshot(&p, Some(id)).unwrap());
            let (_, b) = heap::measure(|| candidate::snapshot(&p, Some(id)).unwrap());
            assert_eq!((a.bytes, a.calls), (b.bytes, b.calls));
        }
    }
}

#[test]
fn last_valid_selected_sample_in_physical_order_and_bad_utf8() {
    let d = tempfile::tempdir().unwrap();
    let p = d.path().join("events");
    let id = new_session_id();
    let mut lines = vec!["\u{2002}\r".to_owned()];
    for (sid, n, k) in [(id, 80, 10), (id, 4, 3), (new_session_id(), 30, 8)] {
        lines.push(serde_json::to_string(&usage(sid, n, k)).unwrap());
    }
    let mut malformed = serde_json::to_value(usage(new_session_id(), 12, 4)).unwrap();
    malformed["event"]["TokenUsageUpdated"]["usage"]["categories"][0]["source"] = "bogus".into();
    lines.push(malformed.to_string());
    lines.push("{".into());
    std::fs::write(&p, lines.join("\n")).unwrap();
    for session in [Some(id), Some(new_session_id()), None] {
        let a = baseline::snapshot(&p, session).unwrap();
        let b = candidate::snapshot(&p, session).unwrap();
        assert_eq!(
            serde_json::to_vec(&a).unwrap(),
            serde_json::to_vec(&b).unwrap()
        );
        assert!(
            b.diagnostics
                .iter()
                .any(|s| s == "skipped 2 malformed event log lines")
        );
        if session == Some(id) {
            let u = b.latest_usage.unwrap();
            assert_eq!(
                (u.model_name.as_str(), u.timestamp_ms, u.categories.len()),
                ("model-4", Some(4), 3)
            );
            assert_eq!(u.actual.unwrap().cached_input_tokens, Some(20));
        } else {
            assert!(b.latest_usage.is_none());
        }
    }
    File::options()
        .append(true)
        .open(&p)
        .unwrap()
        .write_all(&[b'\n', 255])
        .unwrap();
    let a = baseline::snapshot(&p, Some(id)).unwrap_err();
    let b = candidate::snapshot(&p, Some(id)).unwrap_err();
    assert_eq!(format!("{a:#}"), format!("{b:#}"));
}
