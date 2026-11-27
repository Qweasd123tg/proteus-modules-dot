# Reuse bounded scratch during snapshot prefix verification

On the second pass of a historical snapshot comparison, reuse the
existing bounded JSONL scratch mechanism across split lines. The
earlier prefix fingerprint and reset are unchanged. The second pass
still decodes through EOF and applies semantic validation to records
through the requested cut. SQLite continues to use its original reader.

Exact Modules basis: `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. On 12 inline JSONL rows of about
72 KiB each, the second pass went from 477 to 454 Rust
allocation and reallocation requests in both warm and strict fallback
cases. Each whole request still decoded 24 records and traversed the
same input bytes. SQLite was unchanged. Both arms passed 117 tests
(one ignored) and built standalone optimized libraries.

This is independent of #861, which targets the **first** scan. The
receipt records exact pairwise source apply and rollback. No elapsed
time or peak-memory claim.
