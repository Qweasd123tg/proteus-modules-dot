# Sent-image preview recovery: bounded reconnect rearm proposal

## Status and provenance

**Source-only, uncompiled proposal for an existing finding, not a new bug report or a completed recovery fix.** This follows the first image-preview finding in PR85's `round8-desktop/REPORT.md`. The historical report describes its own extracted-source probe; that earlier result is not a test of this patch, and was not rerun here.

Target: `Proteus-harness/Proteus-desktop` at `7eaf70c67dabba8595d98029c875ffc3f59209ad`. Delivery dedup baseline: `Qweasd123tg/proteus-modules-dot` at `6f96ba81cddc76e19751ccdcb8cc041402343357` (through #150). Both refs were unchanged at the final source check. Twelve inspected Desktop files match the pinned Git tree blobs; identities are in `SOURCE-BLOBS.tsv`. The prior report's exact Git blob is `ad4ed594e3b558a9f8d44ca69bcb4511abcb1bc5`.

This changes neither upstream nor live data. The patch is independently reviewed source. Rust, Cargo and rustfmt are absent. **All five newly proposed Rust tests are NOT COMPILED / NOT RUN.** No actual HTTP, image fetch/decode, native scene, real attachment, backend or provider was run. Textual patch checks do not establish Rust correctness.

## Existing failure and the common state invariant

At the pinned source:

- `images/schedule.rs:100-127` folds both HTTP and decode errors into `Stored::Failed`.
- `images.rs:79-128` suppresses another request for the same Failed key. Repeated rendering alone therefore does not retry it. `retain` at lines 70-77 retains slots whose image IDs remain in the transcript.
- `pump.rs:74-84` recognizes recovery by reading `link_error` before `stream_connected()` clears it, but only reloads config. It does not rearm failed previews.

Simply clearing current failures at reconnect misses the opposite ordering: an already scheduled request can complete with an error after reconnect and become sticky then. The proposal makes both orderings obey one small state rule: **one recovery boundary may grant the current preview attempt another demand-driven opportunity, without making every render a retry trigger.** This is preview availability, not loss or repair of the original attachment.

## Minimal policy and implementation

Only the existing `Connected` branch whose preceding `link_error` is present calls `SentImages::rearm_after_reconnect`:

| Current slot | Reconnect effect |
| --- | --- |
| Failed | Waiting, eligible on the next demanded row render |
| Loading | Set one private `rearm_on_failure` boolean |
| Ready or Waiting | Unchanged |

A matching completion consumes the boolean. Success remains Ready. Failure with the credit becomes Waiting; ordinary failure remains Failed with its reason. The existing key/ticket/Loading check still precedes cache insertion and state mutation. Every slot created by `fetch_images` starts with false, so the replacement attempt can fail back to the usual sticky error state. Several reconnects before one completion coalesce, and duplicate Connected without a prior link error grants nothing.

This is explicitly **scheduled-before-reconnect**, not HTTP-started-before-reconnect: admitted work waiting in the queue also gets the credit, even if its HTTP begins after recovery. Repeated distinct reconnects can grant further opportunities. There is no fixed total lifetime retry cap or global request-rate bound. Permanent decode failures may also retry after reconnect because error classification is deliberately unchanged.

Rearming itself submits no work. The existing row path calls `missing` (`thread.rs:158`) and `fetch_images` (`thread.rs:278`). The production pump notifies after a shown update, and Connected returns true. These source connections make later demand possible; **they do not demonstrate native retained-scene/list redraw or an actual successful retry**. Hidden rows remain demand-driven. Image-only errors with healthy SSE remain outside the fix; manual retry, transient/permanent classification and backend rebind are not added.

One private completion helper owns credit consumption and outcome assignment. There is no new queue, timer, retry framework, wire contract or dependency. Queue admission, weak owners, maximum running/pending values, reservation release and capacity wakeups are untouched.

## Cost and composition

Four changed files: **+187 / -7 lines**, comprising **+33 / -7 production lines** and **+154 test lines** (including two existing fixture-field initializers). This is not a line-count or performance optimization. It adds one boolean per retained slot, one O(retained slots) scan at an observed recovery boundary, and potentially extra HTTP/decode work through the existing bounded queue. The actual structure size, latency, CPU and memory were not measured.

This is a follow-up candidate for known PR85 behavior. PR131's workflow media proposal and PR150's active-pane document projection address different paths; neither is a dependency of this four-file diff. This does not claim full runtime compatibility with the larger candidate stack or close OTM-1.

## Proposed tests and honest boundaries

Five new unit tests are included in `images/tests.rs`:

1. Ordinary failure remains suppressed across repeated `missing` calls; reconnect makes it eligible.
2. A late failure consumes one coalesced credit; a manually constructed replacement without credit fails normally.
3. Success after a granted credit remains Ready and consumes it.
4. Ready/Waiting and key/ticket/owner identity are preserved; stale ticket/connection fails the existing predicate.
5. Direct `Chat::apply` with a synthetic `TestAppContext` and API=None checks initial Connected, Disconnected, recovery Connected and duplicate Connected.

The last fixture follows the existing pump test's `Chat::base` pattern. Static inspection of `mod.rs:265-362,445-446` and `actions.rs:15-18` shows API=None makes `supports_core` false, so reconnect returns from `load_config` before a request; `Chat::call` separately checks API before spawning work. This is a source fact, not an executed no-network assertion.

The tests do not exercise actual queue admission for the replacement, the production asynchronous completion closure with a stale result, event-pump delivery, bitmap decoding or native row redraw. `Weak::new()` in the success tests is only a state marker, not a real bitmap. Existing tests were not rerun. No Python behavioral reimplementation is offered as Rust evidence.

## Verification performed and remaining gate

Performed: exact source Git-blob checks; exact historical report blob check; forward and reverse `git apply --check --whitespace=error-all`; strict position/context textual reconstruction; byte comparison against the candidate, including unchanged inspected files; independent design, exact-diff and final-prose review. Details and hashes are in `SOURCE-TEXT-CHECKS.json`, `CHANGES.json` and `REVIEW.md`.

Before production use: format and compile with the repository's pinned toolchain; run the focused image/pump tests and applicable Desktop checks; use controlled local failures to verify both completion/reconnect orderings through the real queue and retained UI, including queued work, stale completion, hidden rows, permanent decode errors and duplicate Connected. Do not infer image recovery from the synthetic state tests alone.
