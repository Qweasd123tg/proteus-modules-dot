# Reuse JSONL scratch when reconciling a commit

The commit-status scan borrows the existing bounded line buffer once per
request. Still validates all rows after a match and preserves the original
acknowledgement and revision. SQLite keeps its existing reader.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`; full-index apply and reverse verified.
Two unmasked optimized storage libraries built. On each scoped native
arm 117 tests passed and one was ignored. For a typed
status lookup across 12 long inline JSONL lines, allocator requests went
557→530 and cumulative requested bytes 3611977→2111180. Both arms
decoded 12 records; misses also scanned all 12. A later sequence mismatch
still failed for both a hit and a miss without modifying the journal.
No elapsed time or process memory measurement.
