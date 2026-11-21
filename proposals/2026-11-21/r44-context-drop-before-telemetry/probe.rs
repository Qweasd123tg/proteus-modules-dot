use app_server::AppContextHistorySummary;
use domain::{
    Event, EventContext, EventEnvelope, SessionId, ToolResult, new_session_id, new_thread_id,
};
use model_standard::{CanonicalMessage, MessageRole};
pub(crate) use proteus_contracts::{domain, model_standard};
use std::{fs::File, io::Write, path::Path};

mod app_server {
    pub(crate) use proteus_contracts::app_protocol::*;
    include!("path_utils.rs");
}
mod core {
    mod context_summary;
    pub(crate) use context_summary::summarize_context_history;
}
mod heap {
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        cell::Cell,
    };

    // Count successful requests/frees on the calling thread only; no sampled RSS or
    // double-counting of old and new blocks during successful realloc.
    #[derive(Clone, Copy, Debug, Default)]
    pub(super) struct Stats {
        pub live: isize,
        pub peak: isize,
        pub total: usize,
    }
    thread_local! { static STATS: Cell<Option<Stats>> = const { Cell::new(None) }; }
    fn change(new: usize, old: usize) {
        let _ = STATS.try_with(|s| {
            if let Some(mut v) = s.get() {
                v.live += new as isize - old as isize;
                v.peak = v.peak.max(v.live);
                v.total += new;
                s.set(Some(v));
            }
        });
    }
    struct Count;
    #[global_allocator]
    static ALLOC: Count = Count;
    unsafe impl GlobalAlloc for Count {
        unsafe fn alloc(&self, l: Layout) -> *mut u8 {
            let p = unsafe { System.alloc(l) };
            if !p.is_null() {
                change(l.size(), 0)
            }
            p
        }
        unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
            let p = unsafe { System.alloc_zeroed(l) };
            if !p.is_null() {
                change(l.size(), 0)
            }
            p
        }
        unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
            let q = unsafe { System.realloc(p, l, n) };
            if !q.is_null() {
                change(n, l.size())
            }
            q
        }
        unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
            unsafe { System.dealloc(p, l) };
            change(0, l.size());
        }
    }
    pub(super) fn measure<T>(f: impl FnOnce() -> T) -> (T, Stats) {
        STATS.with(|s| assert!(s.replace(Some(Stats::default())).is_none()));
        let out = f();
        (out, STATS.with(|s| s.replace(None).unwrap()))
    }
}
macro_rules! version {
    ($v:ident) => {
        mod $v {
            use crate::{app_server::*, *};
            mod context_map;
            pub(super) fn snapshot(
                path: &Path,
                id: SessionId,
                rows: usize,
                bytes: usize,
                provided: Option<AppContextHistorySummary>,
            ) -> anyhow::Result<AppContextMapSnapshot> {
                let history = (0..rows)
                    .map(|i| {
                        CanonicalMessage::text(
                            if i % 2 == 0 {
                                MessageRole::User
                            } else {
                                MessageRole::Assistant
                            },
                            "h".repeat(bytes),
                        )
                    })
                    .collect();
                context_map::build_context_map_snapshot_with_summary(
                    context_map::ContextMapInput {
                        session_dir: Some(path.parent().unwrap().join("session")),
                        session_id: Some(id),
                        workspace_path: None,
                        activity: None,
                        history,
                        event_log_path: path.to_owned(),
                        diagnostics: vec!["caller".into()],
                    },
                    provided,
                )
            }
        }
    };
}
version!(baseline);
version!(candidate);

fn write_event(path: &Path, id: SessionId, bytes: usize) {
    let event = EventEnvelope::new(
        EventContext::new(id, new_thread_id(), None),
        1,
        Event::ToolFinished {
            result: ToolResult::ok("id".into(), "x".repeat(bytes)),
        },
    );
    let mut f = File::create(path).unwrap();
    serde_json::to_writer(&mut f, &event).unwrap();
    writeln!(f).unwrap();
}
#[test]
fn cold_context_high_water_and_identical_response() {
    let dir = tempfile::tempdir().unwrap();
    for (i, (rows, row_bytes, event_bytes)) in [
        (0, 0, 1024),
        (64, 65536, 1024),
        (64, 65536, 1024 * 1024),
        (128, 65536, 4 * 1024 * 1024),
    ]
    .into_iter()
    .enumerate()
    {
        let path = dir.path().join(i.to_string());
        let id = new_session_id();
        write_event(&path, id, event_bytes);
        let (old, a) =
            heap::measure(|| baseline::snapshot(&path, id, rows, row_bytes, None).unwrap());
        let (new, b) =
            heap::measure(|| candidate::snapshot(&path, id, rows, row_bytes, None).unwrap());
        assert_eq!(
            serde_json::to_value(&old).unwrap(),
            serde_json::to_value(&new).unwrap()
        );
        assert_eq!(new.history.messages, rows);
        assert_eq!(new.tools.finished, 1);
        assert!(new.diagnostics.iter().any(|s| s.contains("history-only")));
        println!(
            "history_bytes={} event_output={} peak_before={} peak_after={} requested_before={} requested_after={}",
            rows * row_bytes,
            event_bytes,
            a.peak,
            b.peak,
            a.total,
            b.total
        );
        // In these fixtures old has input history and decoded event simultaneously;
        // the new high-water may still be the creation of history itself.
        if event_bytes >= 1024 * 1024 {
            assert!(a.peak - b.peak >= (rows * row_bytes).min(event_bytes) as isize);
        }
    }
}
#[test]
fn summary_precedence_diagnostics_and_error() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("events");
    let id = new_session_id();
    let preset = AppContextHistorySummary {
        messages: 999,
        estimated_tokens: 123,
        ..Default::default()
    };
    for fixture in [None, Some(&b" \n{} \nmalformed\n"[..]), Some(&[255][..])] {
        if let Some(bytes) = fixture {
            std::fs::write(&path, bytes).unwrap();
        }
        for summary in [None, Some(preset.clone())] {
            let a = baseline::snapshot(&path, id, 1, 12, summary.clone());
            let b = candidate::snapshot(&path, id, 1, 12, summary.clone());
            match (a, b) {
                (Ok(a), Ok(b)) => {
                    if let Some(expected) = summary {
                        assert_eq!(b.history, expected);
                    } else {
                        assert_eq!(b.history.messages, 1);
                        assert_eq!(b.history.user_messages, 1);
                    }
                    assert_eq!(
                        serde_json::to_value(a).unwrap(),
                        serde_json::to_value(b).unwrap()
                    );
                }
                (Err(a), Err(b)) => {
                    assert_eq!(format!("{a:#}"), format!("{b:#}"));
                    assert!(a.to_string().contains("failed to read"));
                }
                _ => panic!("differential outcome"),
            }
        }
    }
}
