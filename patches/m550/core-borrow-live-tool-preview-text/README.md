# Borrow tool result text before making the live preview

The active Core turn projection borrows the first nonempty direct error or
output string instead of cloning it in full before building the same
10,000-byte UTF-8-safe preview. Whitespace, structured/status fallback,
metadata, event routing, durable effects and original results are unchanged.

Apply `source.patch` only to the exact Core owner tree and two recorded source
preimages in `receipt.json`. No alternate source variant is qualified.

The exact TurnProgress modules and pinned Contracts passed 16 stock tests,
17 candidate tests and one paired witness. Seven inert typed ToolFinished
controls produced identical serialized snapshots. In the isolated witness with Rust's standard
library linked statically, the 32 KiB direct output needed 32,768 fewer requested
allocator bytes (43,143 to 10,375) in the apply call. The >256 KiB fixtures
are direct typed projection stress, not normal default-tool payloads.
The two fallback controls retained their request counts and byte totals.

These are allocator requests during the isolated update, not peak/live memory,
Desktop behavior, CLI/IPC, elapsed time or a complete Core build.
