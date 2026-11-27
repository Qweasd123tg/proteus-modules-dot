# Reuse a journal path buffer when checking the WAL stamp

Use spare capacity in the existing valid UTF-8 journal path for the
`-wal` suffix; otherwise keep the exact former lossy name construction.
The same metadata probes run in journal, WAL, manifest order. An empty
WAL is still equivalent to no WAL for stamp comparison.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. In unmodified optimized libraries,
five warm catalog calls on each backend consistently removed one fresh
allocation and one reallocation per call (214/428 requested bytes for
JSONL, 215/430 for SQLite, respectively). Writer-backed OpenSnapshot
removed twice those counts. Direct native stamps agreed with an
independent legacy path/stamp oracle including absent/empty/nonempty
WAL and a distinct Unix invalid UTF-8 negative control. Short paths
without spare capacity used the old branch. 117 tests passed and one
was ignored per arm. No OS-probe, app latency or peak memory claim.

Use source.patch for the exact base; the receipt contains source-only
exact-tree alternates after #850, #888, or both. Do not stack selectors.
