use super::super::{height_cache::HeightCache, height_map::HeightMap};
use super::*;
use crate::meter;

const TOTAL: usize = 50_000;
const DENSE: usize = 16_000;

fn key(id: &str, prefix: usize) -> Key {
    Key {
        identity: hash(id),
        revision: hash("before"),
        layout: hash("same-layout"),
        prefix,
        base: None,
    }
}

fn feed(cache: &HeightCache, key: Key) -> Snapshot {
    cache.bind(key).unwrap().recv_blocking().unwrap().unwrap()
}

/// Seed the genuine on-disk format; reads then go through the actual
/// global Store background worker and HeightCache import/admission.
///
/// At 16,000 records the persisted prefix is 48,000 of 50,000 rows.
fn reopen(
    label: &str,
    count: usize,
    total: usize,
    restore: impl FnOnce(&mut Key),
    protected: std::ops::Range<usize>,
    prior_update: impl FnOnce(&mut HeightMap, usize),
    expect_reject: bool,
) {
    let mut spans = Vec::new();
    let mut rows = 0;
    for i in 0..count {
        let n = i % 5 + 1;
        let height = match i % 67 {
            0 => -0.0,
            1 => 0.0,
            2 => (i % 51) as f64 + f64::EPSILON,
            _ => (i % 101) as f64 * 0.1234567 + 32.25,
        };
        spans.push(ColdSpan {
            rows: n,
            pixels: height * n as f64,
            kind: (i % 3) as u8,
        });
        rows += n;
    }
    assert!(rows <= total);
    let mut key = key(label, rows);
    let writer = Store::start(cache_dir().unwrap(), preferences_dir()).unwrap();
    writer.submit(Snapshot::new(key.clone(), spans, writer.reserve().unwrap()));
    // Drain a genuine prior worker's debounced write and close it before
    // the reopening cache binds and issues a fresh background read.
    writer.shutdown(Duration::from_secs(3));
    assert!(writer.shared.state.lock().unwrap().finished);

    restore(&mut key);
    let cache = HeightCache::new(total, 89.731);
    cache.mutate(protected.clone(), 2_750, prior_update);
    let loaded = feed(&cache, key.clone());
    let loaded_prefix = loaded.key.prefix;
    if expect_reject {
        let mut changed = key;
        changed.layout = hash("changed while read was outstanding");
        assert!(
            cache
                .bind(changed)
                .unwrap()
                .recv_blocking()
                .unwrap()
                .is_none()
        );
    }
    let (accepted, alloc) = meter::measure(|| cache.import(loaded, total, protected.clone()));
    assert_eq!(accepted, !expect_reject);
    cache.read(|map| {
        assert_eq!(map.total_rows(), total);
        assert!(map.span_count() <= MAX_SPANS);
        let mut digest = Sha256::new();
        for row in 0..=total {
            let px = map.prefix(row);
            digest.update(px.to_bits().to_le_bytes());
            let point = map.lookup(row);
            digest.update(
                point
                    .map_or(u64::MAX, |(height, _)| height.to_bits())
                    .to_le_bytes(),
            );
            digest.update([u8::from(point.is_some_and(|(_, fresh)| fresh))]);
            digest.update(
                map.estimate(row)
                    .map_or(u64::MAX, f64::to_bits)
                    .to_le_bytes(),
            );
            for pixel in [px.next_down(), px, px.next_up()] {
                let (r, frac) = map.target(pixel).unwrap_or((usize::MAX, f64::NAN));
                digest.update(r.to_le_bytes());
                digest.update(frac.to_bits().to_le_bytes());
            }
        }
        for span in map.cold_spans(total) {
            digest.update(span.rows.to_le_bytes());
            digest.update(span.pixels.to_bits().to_le_bytes());
            digest.update([span.kind]);
        }
        println!(
            "M401_GEOMETRY {label} {} {} {} {} {} {} {} {} {} {} {:x}",
            alloc.requests,
            alloc.bytes,
            alloc.live,
            alloc.peak,
            alloc.largest,
            accepted,
            loaded_prefix,
            map.span_count(),
            map.revision(),
            map.accounted_bytes(),
            digest.finalize()
        );
    });
    cache.unbind(); // no fixture write caused by owner drop
}
#[test]
fn disk_worker_to_height_cache_import() {
    reopen(
        "dense50000",
        DENSE,
        TOTAL,
        |_| {},
        49_950..TOTAL,
        |_, _| {},
        false,
    );
    reopen(
        "dense_with_native50000",
        DENSE,
        TOTAL,
        |_| {},
        49_950..TOTAL,
        |m, a| {
            assert!(m.set_limited(23_998, 127.3, a, 23_998..24_002));
            assert!(m.set_limited(23_999, 127.3, a, 23_998..24_002));
            m.exclude_disk(24_000..24_002);
            assert!(m.set_limited(24_001, 69.1, a, 23_998..24_002));
        },
        false,
    );
    reopen(
        "partial_base50000",
        DENSE,
        TOTAL,
        |k| {
            k.base = Some((k.revision, 3_719));
            k.revision = hash("new canonical revision");
        },
        49_950..TOTAL,
        |_, _| {},
        false,
    );
    reopen(
        "small50",
        15,
        50,
        |_| {},
        2..20,
        |m, a| {
            assert!(m.set_limited(2, 90.9, a, 2..20));
            m.exclude_disk(4..7);
            assert!(m.set_limited(5, 73.2, a, 2..20));
        },
        false,
    );
    reopen(
        "pressure50000",
        MAX_SPANS,
        TOTAL,
        |_| {},
        200..1_500,
        |m, a| {
            // Fill protected native geometry while the read is going on. The
            // max-span reserve forces genuine pre/post-import compaction.
            for row in (200..1_500).step_by(2) {
                assert!(m.set_limited(row, (row % 17) as f64 * 0.593 + 77.7, a, 200..1_500));
            }
        },
        false,
    );
    reopen(
        "stale_result50000",
        DENSE,
        TOTAL,
        |_| {},
        49_950..TOTAL,
        |_, _| {},
        true,
    );
}
