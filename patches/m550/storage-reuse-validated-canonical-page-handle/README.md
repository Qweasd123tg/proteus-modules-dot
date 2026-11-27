# Reuse a validated compact handle in a canonical page reply

Like display paging, canonical paging can move the three exactly
validated snapshot strings into its reply when they have no spare
capacity. Over-reserved handles keep the trusted compact copy. Handle
identification, journal checks, byte budgets and page cursors are unchanged.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. Both exact arms passed
117 tests (one ignored) and optimized library builds.
In the compact terminal-page fixture, JSONL requested 4→1
Rust allocations and SQLite 5→2; the response retained none of
the oversized request string buffers in the over-reserved control.
No app timing or process memory measurement.
