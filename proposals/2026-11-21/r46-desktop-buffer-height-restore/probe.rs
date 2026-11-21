// Included as a child of the original height_store module by verify.sh.
use super::*;
use std::time::Instant;

#[test]
#[ignore = "synthetic warmed-file microbenchmark, invoked separately"]
fn real_load_probe() {
    let root = std::env::temp_dir().join(format!("r46-heights-{}", uuid::Uuid::new_v4()));
    struct Delete(PathBuf);
    impl Drop for Delete {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    let root = Delete(root);
    let pool = Arc::new(AtomicUsize::new(0));
    for (name, count, keep, base) in [
        ("small-full", 16, 16, false),
        ("page-full", 200, 200, false),
        ("large-full", MAX_SPANS, MAX_SPANS, false),
        ("large-base-8", MAX_SPANS, 8, true),
        ("large-base-200", MAX_SPANS, 200, true),
    ] {
        let original = Key {
            identity: hash(name),
            revision: hash("original"),
            layout: hash("layout"),
            prefix: count,
            base: None,
        };
        let spans: Vec<_> = (0..count)
            .map(|i| ColdSpan {
                rows: 1,
                pixels: 32.25 + (i % 64) as f64 / 4.,
                kind: (i % 3) as u8,
            })
            .collect();
        let sent = Snapshot::new(original.clone(), spans, reserve(&pool).unwrap());
        assert!(disk::save(&root.0, &sent, MAX_DISK_BYTES, MAX_FILES).unwrap());
        let mut requested = original;
        if base {
            requested.base = Some((requested.revision, keep));
            requested.revision = hash("replacement");
        }
        let warm = disk::load(&root.0, requested.clone(), reserve(&pool).unwrap())
            .unwrap()
            .unwrap();
        assert_eq!(
            (warm.key.prefix, warm.spans.as_slice()),
            (keep, &sent.spans[..keep])
        );
        assert_eq!(warm.key.revision, requested.revision);
        let capacity = warm.spans.capacity();
        let retained = capacity * std::mem::size_of::<ColdSpan>();
        drop(warm);
        drop(sent);
        let mut elapsed = Vec::new();
        for _ in 0..33 {
            let key = requested.clone();
            let permit = reserve(&pool).unwrap();
            let begin = Instant::now();
            let loaded = disk::load(std::hint::black_box(&root.0), key, permit)
                .unwrap()
                .unwrap();
            elapsed.push(begin.elapsed().as_nanos());
            assert_eq!(loaded.spans.len(), keep);
            std::hint::black_box(&loaded);
        }
        assert_eq!(pool.load(Ordering::Relaxed), 0);
        elapsed.remove(0);
        elapsed.sort_unstable();
        let n = elapsed.len();
        println!(
            "R46\t{name}\t{count}\t{keep}\t{capacity}\t{retained}\t{}",
            (elapsed[n / 2 - 1] + elapsed[n / 2]) / 2
        );
    }
}
