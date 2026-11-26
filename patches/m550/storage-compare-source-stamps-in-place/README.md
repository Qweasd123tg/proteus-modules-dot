# Avoid allocating a temporary Vec for durable catalog stamp checks

Compare the three fresh journal, WAL and manifest stamps directly on the
durable catalog's read and write fences. Owned catalog stamps, disk format,
complete filesystem observations, error semantics and check ordering remain
unchanged. No stat call or replay is removed.

Apply `source.patch` to exact Modules commit `6b290ebff828427ab66ef9c4ff3b24cef3627603`.
For the three exact prior trees listed in `receipt.json`, select only the
embedded visibility-aware variant. Full-index apply and reverse checked.
Four optimized scoped storage library arms built; 115 tests
passed and one ignored in each. Reopen and publication exercise real JSONL and
SQLite fixtures; stale manifest, WAL normalization, and malformed stamp lengths
continue to miss. Successful publication writes identical bytes for unchanged input.

| Native durable operation | Requests | Requested bytes |
| --- | ---: | ---: |
| jsonl/load | 46 → 45 | 10521 → 10281 |
| jsonl/save | 32 → 31 | 9399 → 9159 |
| sqlite/load | 46 → 45 | 10614 → 10374 |
| sqlite/save | 32 → 31 | 9491 → 9251 |
Measured Rust allocator traffic, not peak or resident memory. This isn't a
whole Desktop startup benchmark.
