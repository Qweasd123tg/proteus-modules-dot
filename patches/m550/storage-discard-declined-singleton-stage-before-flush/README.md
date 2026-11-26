# Do not flush an already declined private display stage

The existing oversized singleton check now uses the exact staged byte
count before finalizing the writer. For that same already-declined
case, discard the anonymous temporary stage without flushing its
buffer. Earlier stage writes, semantic validation, catalog update and
canonical fallback are not changed. Accepted projections still finish
normally.

Exact Modules `5377853779ae499b03ff152b97eb1c11eaa64ed2`; full-index apply and reverse verified.
Two optimized unmasked storage libraries built. 116 tests passed and
one ignored per arm. Actual typed view requests returned the same
declined and successful shapes and exact canonical read. In the owned
test fixtures, finalizing a declined stage previously added 95
bytes (JSONL) and 95 bytes (SQLite) to its private scratch file;
both grew by zero after the patch. This is scoped final buffering,
not a measure of disk transfers or total startup.
