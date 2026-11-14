# Focused Desktop behaviour audit

Date: 2026-11-12 UTC. Repo: Proteus-harness/Proteus-desktop.
Pinned and rechecked main: 75bf201764278eac4b50d156650edcf1429101ff.
No production changes, remote writes, GUI or real-model calls.

## P2: Failed concurrent message can disappear without restoring draft or showing error

Verified against unmodified `src/ui/chat/feedback/mod.rs`, included by path into a small Rust executable with the exact production `proteus-contracts` Git pin (5e8b6ae). The 10 existing Feedback tests pass; the new regression fails.

Steps:
1. Quickly send A and B with identical text. They may have different pasted images both called clipboard.png.
2. Independent background HTTP tasks permit B to reach Core first. B succeeds and its `UserMessageSubmitted` arrives before A.
3. `Feedback::submitted` finds the first unobserved send by text and image names, so marks A observed, not B.
4. A request fails before being accepted by Core.
5. `Feedback::complete(A,false,None)` returns false. `actions.rs` then returns before both draft restoration and `show_notice`, losing A's distinct attachment and hiding its failure.

Evidence:
- https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/feedback/mod.rs#L72-L98
- https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/actions.rs#L136-L174
- `feedback.log`: actual unchanged production method returns false for A restoration.
- `feedback-tests.log`: 10 existing passed, 1 new regression failed.

Run: `source /workspace/shared/proteus-toolchain/env.sh; cargo test --manifest-path audit-repros/Cargo.toml`

Suggested repair: carry durable client request/message identity in stream admission events and match by it. If identity cannot be proven, do not treat matching text/name as proof a failed request was delivered. Add out-of-order response/echo + same-name different-image regression. No fix made.

## P2, source-level: Native Codex history can silently skip a span while catching up to a growing live tail

This concerns the direct/native Codex driver, not Proteus's Codex model profile. No GUI reproduction claimed. A deterministic source-derived paging trace demonstrates the bookkeeping; an actual native test is still needed.

Steps:
1. Open a Codex chat with items1..500. Live window is451..500.
2. Pause reading, let more items arrive; `pause_codex_before_eviction` retains original window.
3. Page upward far enough that 200-row budget evicts page0(451..500). Archive251..450; newest_page=1.
4. Meanwhile server reaches item600.
5. Scroll down toward newer history. Code computes index=0 and cursor_chain[0]=None, then calls `thread/items/list(cursor:null,limit:50,desc)`.
6. Returned551..600 append directly to old archive.451..550 are skipped with no missing-page notice. Next Newer jumps to live because newest_page==0.

Why: original page0 has no stable reload anchor; None means latest now, not the historical page0. Newer response is never checked for adjacency.

Sources:
- https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/codex/history.rs#L9-L40
- https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/codex/history.rs#L82-L109
- https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chat/codex/history.rs#L179-L240
- https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/agents/codex/mod.rs#L404-L430

Run source-derived model: `python3 audit-repros/codex_paging_trace.py`. Output: skipped451..550,100 rows. This model is not a replacement for native testing.

Suggested repair: retain opaque boundary identity for evicted original tail, paginate until adjacent to that identity and then bridge to live. Test paused reader, >200 old rows, >50 new incoming items, down/up return without omissions/duplicates.

## Coverage and exclusions

Read focused chat send/feedback, stream cursor and pump, Proteus history paging, Codex history/state/projection, tab/resume ownership and attachment paths. Did not rerun all Desktop, native rendering, actual external Codex, or live LLM. Found and rejected weaker candidates after tracing their producers. No full-audit claim.
