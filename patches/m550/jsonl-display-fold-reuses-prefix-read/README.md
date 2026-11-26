# Fuse the JSONL display snapshot fingerprint with its strict fold

For a stable Unix JSONL source, reuse the same pinned replay used by ordinary
storage snapshots. Strict validation computes the unchanged fingerprint while
reading the journal. There is no separate full-prefix read/hash before it.
The temporary display stage and fold belong to one attempt: on a version
change they are discarded, the same pinned prefix is verified, and a fresh
stage is built. A legitimate appended suffix does not become part of that
snapshot. SQLite and non-Unix still use their previous capture strategy.

Apply the standalone source patch to Modules
`4fa39c3ce94119e36f3ff4a86e28dd2171342aba`. No prior exact selector through
#827 overlaps the three source paths. No storage schema, journal, cache
format, or response changes. Blob decoding/validation and staging limits
remain in place.

In the actual native storage service, a synthetic 20-Append, 1,213,622-byte
journal went from 1,213,622 separate fingerprint-read bytes to zero. Both
arms still read/replayed 1,213,622 bytes and decoded 20 records. The exact
per-arm journal hash, visible typed messages and page identities passed.
An independent native retry test appends during the first attempt and
checks creation of a new stage, unchanged boundary, and fixed page contents.

The pinned storage suite passed 105 tests in both arms (one existing
ignored; includes a shared instrumentation fixture). The additional
retry test passed separately. This is a removed full read/hash on the
stable path, not a latency or whole-application PSS benchmark.
