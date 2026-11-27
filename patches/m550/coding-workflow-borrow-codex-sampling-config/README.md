# Borrow Codex sampling retry config

Deserialize the retry settings from the existing JSON Value without
cloning that tree. Strict field handling, diagnostics and the default
and clamp stay unchanged. This patch does not change retry behavior.

Base: Modules f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
Both arms passed three focused offline tests and built as optimized
libraries with the test overlay removed. Accepted config:
2→0 allocator requests, 650→0 requested bytes.
Rejected config with a synthetic nested field:
136→4 requests, 136081→256 requested bytes.
The comparison checks the original config is unchanged, results and
diagnostics match, and no session, tool or provider is contacted.
These are allocator requests for the parser only, not RSS or latency.
