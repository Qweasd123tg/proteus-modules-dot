# Borrow a cached snapshot prefix and move the writer descriptor

A valid in-memory head is borrowed during capture. The resident-writer
bootstrap moves its newly authorized descriptor and observed stamps to
the catalog. The existing describe/format gate, save order, final stamp
comparison, and verification status of each branch stay unchanged.

Current Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. The isolated ownership sites
save two Rust allocation requests (304 bytes) for a memory hit and
5 requests (1065 bytes JSONL; 1066 SQLite)
for resident writer capture. Durable and strict cold paths keep the
same verification and decode counts. Whole-request JSONL also showed
five fewer fresh requests (1,017 bytes) for the writer case and
two (304 bytes) for memory. SQLite whole-request realloc totals varied even in
untouched controls, so the SQLite claim is scoped to those sites.
These are requested bytes, not time, RSS or PSS. Both arms passed 118 tests (one ignored) and
built standalone optimized storage libraries.

Choose one exact source. Use source.patch on the stated base. If already
using draft #850, #871, or both, use the matching exact pre-tree selector
from receipt.json at .overlap.rebased_selectors (check its SHA-256).
All six source orders and inverses were verified. Do not stack source
and an alternate; the alternative trees were not native-run here.
