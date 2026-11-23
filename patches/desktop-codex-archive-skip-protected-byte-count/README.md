# Skip Codex archive byte accounting when the edge page is visible

The Codex history window cannot evict a page overlapping the visible rows.
Check the existing overlap predicate before walking row payloads to count
bytes. Those counts could not lead to an eviction in this branch. Keep the
same 200-row and 8 MiB thresholds, whole-page trimming, visible-range
rebasing, cursor handling, pruning and change ordering.

A dependency-free Rust 1.95.0 test compiled the exact stock and candidate
synchronous history-result callback and the relevant transcript methods
against inert, owned fixtures. Debug and optimized profiles each passed
eight tests covering 18 explicit cases and 320 generated windows. On a
protected 50+50-row window in either direction, row-accounting calls fell
from 100 to zero. After a count-only eviction rebased the viewport onto
the next protected page, calls fell from 200 to zero. Cached and
evictable-page controls kept the same work and results.

This measures avoided row-accounting calls, not bytes retained, elapsed
time, or native app memory. The build did not include GPUI, Codex
transport, or a real session. The proof covers valid archive state and
representable counts; it does not exercise malformed internal state.
