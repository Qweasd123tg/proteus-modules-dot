# Adjacent text-run candidate (not a bounded runtime)

Source: Proteus-desktop `2bf38f67055f10f5ed0fd225399ba77d84756ba1`.
Layer after all three immutable PR23 prerequisites from bundle
`acaadb879a636161a723d0f115cbb39b3f2af0db`: pagination, snapshot-routing tests/extraction,
snapshot-routing fix. No upstream repository modification is part of this bundle.

## Two deliberately separate stages

1. `0001-text-run-seam-and-tests.patch` partitions adjacent compatible text runs,
   but the production pump still calls its original `self.apply` once for each
   original event. Cursor acceptance, mutation, timestamping, layout, observer
   emission, and no-op applications remain interleaved in their original order.
   The only layout extraction shares existing fresh-key/list/affected-chain
   instructions through `RowLayout`; snapshot reply preparation is unchanged.
2. `0002-offset-faithful-text-coalescing.patch` explicitly changes scheduling:
   fold one compatible run, apply one combined layout instruction, then emit
   every original non-None Change in order. This scheduling change is NOT hidden
   in the baseline. Singleton runs call the original reducer, avoiding an
   unnecessary tail buffer.

All original envelopes stay intact. Runs require equal schema/session/thread/
turn/message/phase; seq and timestamp are neither rewritten nor deduplicated.
Every non-text event and connection item is a hard barrier. Every source event
passes through the existing SessionCursor in physical order before folding.
There is no cross-batch buffering to flush on disconnect or queue close.

## Compatibility invariants

The production single-event Transcript reducer is the differential oracle.
The edit representation is `original[..keep] + tail`. Byte offsets are checked
against the CURRENT representation, not the original string; invalid/out-of-range
offsets append exactly as before. Shrinking updates cannot revive discarded text.

Row lookup remains reverse message-ID lookup regardless of role. Existing row
metadata, images, time, key, and other rows' streaming state survive. Creation
occurs only on the first nonempty event; that event's physical timestamp is kept,
one key is allocated, and other rows stop streaming. A later empty truncation
does not erase the newly created row. Empty updates to existing rows still reopen
streaming and emit Updated. Snapshot root routing comes from the prerequisite fix.

## Planned checks; not yet executed

There are 16 added tests: 15 semantic tests and one deterministic work-budget test.
The exhaustive test defines 387,072 real-reducer comparisons across short UTF-8
offset sequences and every partition boundary; this is a planned test count, not
a claim that they have passed.

Baseline: 9 semantic Transcript tests + 6 batch/layout tests must pass; exactly
`transcript::text_run::tests::work_budget_for_adjacent_appends` must fail at its
named work assertion. This is PERFORMANCE WORK evidence, not a functional bug.
Compilation, setup, unrelated panic, or another failed test never counts as the
expected red. After patch2, all16 must pass. Also run the existing Transcript,
native chat, pagination-flow, extension Preparation and formatting checks. The CI also
runs the canonical unfiltered `python3 scripts/test.py -- --test-threads=4` gate.
Its success plus mandatory named PASS records is not an independently enumerated
inventory of every possible platform/feature test.

The new production RowLayout parity test compares append count, fresh keys,
dirty-row union through the actual `affected_rows`, original Change stream and
public extension metadata projection. It includes a System/tool identity collision
inside a three-tool chain. The shared production reply-preparation guard is false
for all text changes and true for a Spliced control. This does not execute async
reply preparation, native ListState anchors, frame timing or pixel rendering.

## Cost model, not a timing benchmark

For an existing K-byte row and n append deltas of d bytes, the original reducer
copies n*K + d*n*(n-1)/2 prior-row-prefix bytes. Within one compatible run, the
candidate copies K prior-row-prefix bytes once. For n64, K4096, d64, the test's
expected values are 391168 -> 4096 prior-row-prefix bytes, 64 -> 1 row-ID lookups,
and 64 -> 1 logical delta row-text replacements.

These counters EXCLUDE tail push/reallocation, tail-to-final-String copies,
String-to-Arc conversion and allocator/RSS effects. They are not total bytes,
allocations, elapsed speedups, paint counts or responsiveness measurements.
Layout collapse is tested as production instructions/effect planning, not included
in the baseline real-Transcript work-budget assertion.

For fixed b-event batches, full-prefix work is still O(n²/b) across batches.
The source batch allocation remains alive while run and Change vectors add O(run
length) auxiliary memory. No RSS improvement is claimed.

## Explicitly unresolved

- Existing unbounded try_recv drain, queue growth, UI fairness and arbitrary
  snapshot size remain unchanged. This candidate provides no hard time/RAM bound.
- Core TurnProgress still appends deltas without honoring Desktop's offset splice
  rule; snapshot/offset parity is a separate unresolved protocol/producer issue.
- Native window/scroller/frame behavior and portable delivery are not qualified
  by these source-level/differential tests.

Local validation so far: exact unified hunks/context/counts applied in memory;
all source blobs and complete Git trees reconstructed; official installed
rustfmt used only through stdin/stdout. No local files, builds, caches or downloads
were written. Rust tests, native window, portable build and timing measurement
have not run. Revised exact source has independent source-level approval; whole baseline-patch digest is author-computed until the runner verifies it and strictly applies it. Native tests remain unexecuted at publication. Publication requires parent approval.
