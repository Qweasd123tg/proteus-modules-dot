# Decide transcript footer and stamp in one pass

One independent Desktop production patch at exact `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 plus Desktop #393, #396, #398, #400 and #401. The same two-file patch applies in both tiers. The R79 gate runs exact source headlessly with synthetic transcript messages, not a native GPUI test.

## Duplicate work in ordinary render

The visible virtual-list callback enters `Chat::render_row`. After existing visibility and compact-chain exits, stock determines `time_after(entries, end, complete_tail)`, which calls `ending`, then calls `ending` again with the same immutable entries, group end and tail state. Even ordinary rows which turn out not to end the turn repeat the next-visible check. When duplicate linked subagent tool rows intervene, that also repeats typed session lookup and the peer search across the displayed transcript.

One `turn_end` result carries footer eligibility and an optional time from the existing lookup. No result means there is no ending. A result with no timestamp is still an eligible footer and can expose copy actions if the unchanged copyability test permits them. Actual render is still gated by `footer && (copyable || time.is_some())`. Same raw row order, next visible predicate, loaded/running tail gate, backward time selection, copyability, render callbacks and time formatting. No new cache, index, allocation, framework change, or invalidation. Hidden-row preflight and clipped-page layout policy are separately invoked and unchanged.

Of 39 hash-verified earlier Desktop receipt patches, only #363 shares a distant folded-header hunk in `thread.rs`. #351's child metadata borrowing is preserved exactly, so this patch avoids repeat calls to that existing code rather than changing its behavior or ownership rules.

## Focused proof scope

The harness compiles the real stamp function, exact `render_row` slice from displayed transcript, visibility and group routing through time/eligible/copyable, then evaluates the unchanged real draw expression. It verifies the footer row key against the actual displayed entry. It runs exact `History::apply`, `accept_seek`, `displayed`, `range`, `row_context`, and transcript DTO ingestion with pinned contracts; child-link matching is the exact stock or cumulative source for that arm. Focus, motion time/drawing, elements and the live session's producer are not executed natively. Static contexts for the renderer continuation and timestamp formatting match across arms. No clock, allocator, RSS, or latency measurement.

Counters are limited to the footer decision: every invocation of tail criteria, the existing next-visible hidden predicates, recognized task link lookups, and their exact peer predicates. The initial row's visibility, row prep, paint, clipboard I/O, and unrelated work are excluded. The counters are test-only, not production instrumentation.

The four baseline/candidate replays passed the same 30 checks with byte-identical trace SHA `d3ed17fdd1603ec3708eeeac51f42f97f78d383295ff155deaca05161f806cd2`. Controls include non-footer rows, timestamp-less eligible copy and no-copy alternatives, last-in-row-order rather than greatest numeric timestamp, active then settled Core tail, real accepted 50-row seek with clipped footer ownership hidden by the last duplicate tool, actual Codex archive priority, malformed/missing/conflicting links, and folded closed/open/moving render branch selection. The moving flag is controlled, not a native animation.

| Executed synthetic path | Tail-policy calls | Next-visible hidden predicates | Recognized link lookups | Peer candidate rows examined |
|---|---:|---:|---:|---:|
| Ordinary reply before the next user | 2 → 1 | 2 → 1 | 0 → 0 | 0 → 0 |
| Two hidden duplicate tool links before the next user | 2 → 1 | 6 → 3 | 4 → 2 | 10 → 5 |
| Incomplete 50-row accepted seek with one hidden suffix tool | 2 → 1 | 2 → 1 | 2 → 1 | 96 → 48 |

The full exact behavior trace is in `behavior.trace`; `work.tsv` lists the other measured paths. In the final admitted attempt, sampled resource growth stayed at or below +2,948 KiB on the target mount and +2,212 KiB on the temporary mount. Cargo JSON records are tied to the exact generated Rust/lock/executable bytes in `cargo-provenance.json`.

## Reproduce

An existing warm offline Cargo cache/target and a common compiler lock are required. Set the absolute paths `CARGO_HOME`, `CARGO_TARGET_DIR`, `R79_BUILD_LOCK` and `R79_RAW_CARGO_DIR` (create the raw directory); use at least 512 MiB free on both mounts, no concurrent builds, and max +200 MiB net growth. The original uses Rust/Cargo 1.95.0, `--offline --locked -j1`, and fresh Cargo JSON executable selection with SHA before/after running each arm.

    bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS
    bash verify.sh --run WORKSPACE_WITH_PINNED_INPUTS
