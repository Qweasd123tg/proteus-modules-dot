# Move existing live Codex delta IDs into the transcript lookup

Each live text, reasoning and tool-output event already owns its turn ID and item ID. Move them from the existing three consuming UI match arms into the unchanged tuple lookup shape. On a lookup miss, reuse the tuple's strings in the same provisional item. Do not copy a delta's text differently or change the lookup, clipping, row keys, status, tool call ID, or relationship to the paused archive probe.

Two small hunks, in src/ui/chat/codex/mod.rs and src/transcript/external.rs, apply unchanged on exact Desktop b6a7ec2d8d7e486c8aba01291aa8c89774c4cded and sealed M150 plus the 57-patch Desktop roster through #436. The neighboring #274/#434 older-page changes and #436 ready pump stay intact. The independent paused archive lookup still behaves as before, including any copies it makes; neither that path nor any approvals, routing, transport, GUI scheduler, status policy, headroom/byte limits or UTF-8 policy are changed.

## Focused measurements

Work meter includes the actual three mechanically lifted UI match arms plus the unchanged original conditional trim. Already built values come from the actual Codex projection; only lookup/append/fallback/trim work is metered, excluding projection, fixtures, output snapshots and teardown.

| Synthetic ready input | Alloc/realloc requests | Aggregate requested bytes |
| --- | ---: | ---: |
| 128 ordinary assistant fragments for the same streaming row | 512 → 256 | 178,467 → 167,971 |
| Three first fragments, tool/reasoning/text, no existing rows | 26 → 14 | 2,961 → 2,851 |
| Three mixed fragments to existing rows | 11 → 5 | 154 → 99 |
| Three ignored fragments to known rows | 6 → 0 | 20 → 0 |
| One fragment with two empty IDs | unchanged | unchanged |

Savings equal one copy of each nonempty ID and its exact UTF-8 byte length for known rows, even if a delta is ignored, and two copies of each for new rows. Text, tool output, retained row bytes and key identity are unchanged. Work counts do not include the already-owned input ID allocation from projection or the separately unchanged paused archive probe. No UI, wall-time, or RSS claim.

## Parity and source binding

Four fresh locked offline artifacts, stock and cumulative baselines/candidates, each 17/17: 13 native transcript external/reasoning tests and four fixture tests. Four complete byte snapshot records matched, including row, tool bytes, keys and identity, order, timestamps, append-bound, state output, Change and trim headroom. Fixtures include ordinary Unicode fragments; identical IDs across different turns; separate reasoning and plain/tool text; stale and completed rows; empty IDs and first empty tool delta (creates the same streaming placeholder with no result); scalar-boundary clipping; non-tool row receiving a tool delta; oversized fallback retaining the existing projected suffix; and prune/reinsert across real 50-row trim. This is a headless test of exact transcript/projection and selected UI expressions, not a native UI test or actual app-server session.

No native GUI, app server, program execution fixture, or remote. Forward/reverse apply, rustfmt and whitespace passed on both exact source tiers. Same 125-package locked warm closure as the preceding transcript proof; one cargo job under the common lock, offline, unchanged 512/256 MiB floors and +200 MiB growth fence. Observed peak growth at fences 6,772 KiB target and 37,060 KiB temporary; sealed Desktop source and lock checked unchanged after the run.
