# Root tool text: preserve full projection across reconnect

**Source-only candidate for the known PR85 root-tool reconnect finding.** No Rust compilation, formatter, tests, HTTP/stdio, Desktop, journal storage or model/tool runtime was executed. Unlike the preceding SQLite proposal, this pass contains no Python behavioral model or runtime probe. No production source or remote refs were changed.

## Baseline and deduplication

- Core main `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules main `c035142558f0fca43e9772fc0e50ca293abf1531`; no Modules source or dependency changes are proposed.
- Delivery main `e05565f63f80f3420c53bb2a68627a87beec871c`, including PR121. PR121 remains a proposal with separate Python SQLite representation evidence, not Rust runtime evidence.
- This is **finding 2** from the [PR85 tool-response report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/e05565f63f80f3420c53bb2a68627a87beec871c/research/proteus-continuous-audit-2026-11-13/evidence/tool-response/findings.md). `PRIOR-ROOT-TAIL.md` contains only that scoped excerpt. Its historical 10017-byte live/snapshot/canonical observation is not a fresh reproduction of this candidate. Finding 1 and its approval/cancellation paths were not investigated.
- PR91–101 state/coherence proposals, PR104 reasoning identity and PR106–121 candidates were checked for overlap. No equivalent root-result retention proposal was found. PR118 delivery/ACK HOLD and PR120 concurrent-drain proposal remain separate. Combined candidate-stack application/build was not performed.

## Current source and scope

`TurnProgress::apply` handles ToolFinished using the existing `ToolResult::text_or_status()` projection and status/metadata. `set_tool_status_in` finds either a flat tool row or a tool nested under a subagent card. Both currently call `update_tool`, which unconditionally takes a UTF-8 prefix of at most 10000 bytes. Thus this preview limit is also applied to flat/root results.

The truncation changes only the live projection, not the original published ToolFinished payload. `SessionView::snapshot_parts` reads that shortened progress; subscription snapshots use it for reconnect and resync. In contrast, `transcript::append_transcript_tool_result` retains the whole text projection. The journal renderer calls this same result projector for eligible root records. An existing foreground-child test explicitly requires a bounded prefix and does not enable `compact`.

This is not canonical data loss or a model-context truncation change. It is a mismatch between the accepted event text, active snapshot, and completed transcript. Native UI rendering is not verified here.

The change applies to existing matched tool cards. Missing-call reconstruction,
call identity, event routing and equality of every transcript field across
arbitrary histories are not new guarantees of this candidate.

## Minimal ownership correction

Move the existing `truncate_utf8` call into the **nested subagent** branch. The common `update_tool` then copies the representation it receives:

- flat/root card: full existing `text_or_status()` result;
- foreground nested child: same UTF-8 prefix as before;
- background nested child: same UTF-8 prefix as before.

`compact` continues to govern background JSON metadata only; tool-argument compaction is untouched. Using `if compact` for the text limit would incorrectly remove the foreground-child cap, so that approach is deliberately not used. The child branch still copies the selected small slice, not a truncated String retaining the original large allocation.

There are no new helper types, policy flags, DTOs, limits, dependencies or frameworks. The production file grows by three lines including comments. The benefit is one correctly placed lossy-preview policy, not fewer LOC or a claim of improved performance. Canonical text/error/structured-fallback precedence, result status, metadata and terminal reference handling remain unchanged.

## Retention cost and honest limits

Full root retention **increases** the live view's retained string bytes for outputs above 10000 bytes, and snapshot cloning copies those additional bytes. For a result text of N bytes and old retained UTF-8 prefix P, the string-length increase is N−P for that retained root row, plus copies made by snapshots. This is a source-level logical byte comparison, not an allocation/RSS or latency measurement.

The text is retained by TurnProgress until its existing reset/settlement lifecycle; this patch does not introduce aggregate byte admission or change cleanup. It must not be justified by a universal 200000-byte guarantee: BoundTools limits `output` and `error`, while the already known structured Text/Json fallback budget gap remains. Direct event producers can also supply larger text. Metadata/argument size is not newly bounded either.

The selected narrow tradeoff aligns root snapshots with the full result projection already used for published events and completed transcript. If a strict bounded full-root view is required instead, an explicit marked-preview/retrieval contract is needed; this patch is not such a design. It does not make child previews lossless or add a truncation marker to them. No broad memory, budget, delivery or persistence guarantee is claimed.

## Proposed controls, NOT RUN

1. `events/tests/tool_results.rs`: six result representations through the existing RuntimeEventSink, live subscription and reconnect subscription: short text, long text with multibyte tail/diagnostic, long error with lower-priority output, structured Text fallback, structured Json fallback and empty success. Compares the root snapshot tool with the completed canonical-message projector, then checks settlement replacement. This is a proposed event/subscription/projection test, **not** a cold on-disk journal or HTTP/GUI scenario.
2. `turn_progress/tests/tool_previews.rs`: foreground and background child cases separately check the same UTF-8 prefix and bounded retained String capacity, while preserving their different JSON args/metadata compaction behavior. This prevents the tempting but wrong `if compact` fix.
3. Existing foreground-child long-output and UTF-8 boundary controls are unchanged. Existing event sequencing/resync and settlement tests are not modified or claimed to have passed.

The first proposed test should distinguish the faulty baseline for long root cases by source reasoning; this expected failure has **not** been executed. The second is a preservation control that can pass the baseline. Two tests alone are not an executed full app-server gate.

## Actual verification

- Twenty Core source blobs are stored and verified against Git blob IDs in `SOURCES.json` / `READ-VERIFICATION.json`.
- `git apply --check --whitespace=error` succeeded on the isolated baseline. Text application produced exact `after/` bytes for six files; `PATCH-VERIFICATION.json` and `MEASUREMENTS.json` record this.
- Exact independent source review is recorded separately. It is not a compiler/runtime result.
- No project scripts, Rust build/formatter/tests, Python runtime model, external services, user sessions or production files were executed/modified.

Before production adoption, compile/format and run affected Core event/progress/transcript tests, verify real reconnect/resync and cold history, and measure the additional live-view retention/snapshot cost on representative large results. The structured fallback cap gap and aggregate retention policy remain separate work, not silently closed by this proposal.

Patch SHA256: `1d505f8937285f5990aa65baf13ee5486003696fa7ca8e2ef568e6a84187d05a`.
