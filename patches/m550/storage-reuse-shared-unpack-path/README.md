# Reuse the path buffer when unpacking shared journal chunks

Reuse one path buffer across unique chunks after the existing lexical
hash check. Each read still opens the exact same path, enforces the same
size limits and verifies the same per-chunk and aggregate hashes. The
repeat index remains local to one unpack; writing is unchanged.

Exact Modules base `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. A retained synthetic
50,000-message external record exercises 528 distinct shared chunks.
Unpack and the typed JSONL decode each save 4748 allocator
requests totaling 906198 requested bytes (including reallocations)
with the same 528 chunk-open attempts. Payload SHA and typed count
are unchanged. The raw case still borrows, A/B/A still opens two files,
and the missing/truncated/overlong/corrupt cases preserve diagnostics.

118 tests passed (one ignored) per arm and both standalone optimized
libraries built. No application latency or peak RAM claim. If applying
alongside earlier #855 or #876, rebind the source to that exact commit
and verify; do not blindly stack full-index patches.
