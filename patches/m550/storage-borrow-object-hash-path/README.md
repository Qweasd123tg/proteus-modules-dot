# Borrow the session image hash when constructing the object path

Validate lowercase ASCII hex directly, without allocating a lowercase
copy. Hash-only reads also avoid cloning the input to construct a
temporary descriptor. All three callers use the same image path,
limits, and content integrity checks as before.

Exact Modules basis: `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. Path-building probes in native typed tests on JSONL
and SQLite measured one fewer Rust allocation (64 requested bytes)
by PutBlob and ReadBlob, and two (128 bytes) for ReadBlobByHash.
The fixture verified exact stored/read data and path, invalid hashes,
byte limits, and bad content. Both arms passed 117 tests (one ignored)
and built standalone optimized libraries. No end-to-end memory or
timing claim.
