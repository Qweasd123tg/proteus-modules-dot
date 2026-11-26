# Compare display snapshot blob stamps without a second map

During OpenDisplaySnapshot, reuse the existing metadata-stamp comparator
after replay instead of collecting a second full map of path/stamp pairs.
Keep the initial map, strict replay, the original source-stamp guard order,
and the later catalog-save guard. No traversal is removed.

Apply `source.patch` on exact Modules `6b290ebff828427ab66ef9c4ff3b24cef3627603`. If the exact #836
after-#815/#825 variant is already applied, use only the embedded display
patch from `receipt.json` instead. Never apply both variants. Apply and
reverse checked on both bases.

Four optimized storage libraries built. Per arm: 116 tests
passed and one ignored. The native synthetic JSONL display path with 261
inventory paths went from 2609 to 2312 Rust allocation/reallocation
requests and 449905 to 407677 total requested bytes. SQLite and no-inventory
controls are in the receipt. Snapshot, pages, journal fingerprint,
and exact written catalog were checked. No Desktop latency or PSS claim.
