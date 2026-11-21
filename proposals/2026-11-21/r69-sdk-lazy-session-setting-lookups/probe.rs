// Appended to the SDK host module only in separate synthetic count builds.
use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

static ROW_CHECKS: AtomicUsize = AtomicUsize::new(0);
static BULK_VECTORS: AtomicUsize = AtomicUsize::new(0);

pub fn selector_probe_snapshot() -> (usize, usize) {
    (ROW_CHECKS.load(Relaxed), BULK_VECTORS.load(Relaxed))
}

pub fn selector_probe_controls() -> Value {
    let mut host = Host::default();
    let mut out = Vec::new();
    for (case, rows, id, pending) in [
        ("empty", 0, "fixture", false),
        ("missing-64", 64, "missing", false),
        ("last-64", 64, "fixture", false),
        ("pending-null", 64, "fixture", true),
    ] {
        let settings: Vec<_> = (0..rows)
            .map(|index| {
                if index + 1 == rows {
                    json!({"id":"fixture","control":{"type":"select","value":"last"}})
                } else {
                    json!({"id":index,"control":{"type":"select","value":index}})
                }
            })
            .collect();
        host.state = Some(json!({"config":{"session_settings":settings}}));
        host.pending.clear();
        if pending {
            host.pending.push(("id".into(), "fixture".into(), Value::Null));
        }
        ROW_CHECKS.store(0, Relaxed);
        BULK_VECTORS.store(0, Relaxed);
        let value = std::hint::black_box(host.setting_value(id));
        let (checks, bulk) = selector_probe_snapshot();
        out.push(json!([case, value.is_some(), value, checks, bulk]));
    }
    Value::Array(out)
}
