#!/usr/bin/env python3
"""Test-only instrumentation. Run in a disposable checkout of base or candidate, then
cargo test --locked -p session-storage --lib queue_cost_probe -- --nocapture --test-threads=1.
Only counts SessionLocator equality calls made to maintain the two eviction queues."""
from pathlib import Path
import sys
repo = Path(sys.argv[1]); service = repo / "storage/session-storage/src/service.rs"
catalog = service.with_suffix("") / "catalog.rs"
views = catalog.with_name("views.rs")
test = catalog.with_suffix("") / "tests.rs"
instrument = """
#[cfg(test)]
thread_local! { static QUEUE_COMPARISONS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) }; }
#[cfg(test)]
fn same_queue_key(x: &SessionLocator, y: &SessionLocator) -> bool {
    QUEUE_COMPARISONS.with(|n| n.set(n.get() + 1));
    x == y
}
"""
def replace(path, old, new):
    data = path.read_text()
    assert data.count(old) == 1, (path, old)
    path.write_text(data.replace(old, new))
assert "fn same_queue_key" not in service.read_text()
service.write_text(service.read_text() + instrument)
if "fn remember_catalog_entry" in catalog.read_text():
    replace(catalog, "if order.back() == Some(&session) {", "if order.back().is_some_and(|old| same_queue_key(old, &session)) {")
    replace(catalog, "order.retain(|old| old != &session);", "order.retain(|old| !same_queue_key(old, &session));")
else:
    replace(catalog, "self.catalog_order.retain(|old| old != &session);", "self.catalog_order.retain(|old| !same_queue_key(old, &session));")
    replace(views, "self.prefix_order.retain(|s| s != &session);", "self.prefix_order.retain(|s| !same_queue_key(s, &session));")
test.write_text(test.read_text() + """
#[test]
fn queue_cost_probe() {
    let (_, _, (summary, prefix)) = pending(&Fixture::new(BackendKind::Jsonl));
    let service = StorageService::new(BackendKind::Jsonl);
    let mut state = service.lock_state().unwrap();
    let mut phase = |name: &str, keys: &mut dyn Iterator<Item=usize>, last| {
        QUEUE_COMPARISONS.with(|n| n.set(0));
        for i in keys {
            let mut summary = summary.clone();
            summary.descriptor.session.key = format!("resident-{i:05}");
            let key = summary.descriptor.session.clone();
            state.remember_prefix(key, prefix.clone());
            state.remember_summary(Vec::new(), summary);
        }
        let key = SessionLocator { key: format!("resident-{last:05}"), ..summary.descriptor.session.clone() };
        assert_eq!(state.catalog_order.back(), Some(&key));
        assert_eq!(state.prefix_order.back(), Some(&key));
        assert!(state.catalog.contains_key(&key) && state.prefixes.contains_key(&key));
        println!("COST {name} queue_comparisons={} summaries={} prefixes={}", QUEUE_COMPARISONS.with(|n| n.get()), state.catalog.len(), state.prefixes.len());
    };
    phase("fill_1024", &mut (0..1024), 1023);
    phase("churn_4096", &mut (1024..5120), 5119);
    phase("refresh_tail_100", &mut std::iter::repeat_n(5119, 100), 5119);
}
""")
