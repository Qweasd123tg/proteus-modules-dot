# Reuse scratch during JSONL prefix hashing

When finding a historical prefix fingerprint, reuse the existing bounded
read scratch instead of recreating it per line. Still read and decode
through the pinned EOF to authenticate the entire journal, not just
the requested prefix. The later semantic verification is unchanged.

Exact Modules `5377853779ae499b03ff152b97eb1c11eaa64ed2`; full-index apply and reverse verified.
Two unmasked optimized storage libraries built. On each scoped native
arm 116 tests passed and one was ignored. In a typed comparison across
12 long inline lines, Rust allocator requests in the first scan
went 447→424, while the full request still decoded 24 records.
Wrong digest was rejected and corruption after the prefix still failed.
No elapsed time, process memory, or disk I/O measurement.
