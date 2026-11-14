# Model SSE ownership and delta handling: source-only candidate

## Result

A small, concrete simplification candidate, not a new functional defect finding and not a system-wide refactor:

1. Give the Anthropic stream sole direct ownership of its parser state instead of wrapping an unshared state in Arc<Mutex<_>>.
2. Combine the byte-identical OpenAI function-tool and custom-tool argument-delta match arms.

No generic adapter framework, new helper, trait, crate, dependency or behavior default is introduced. No upstream production files or Git refs were modified.

## Exact source scope

- Modules main freshly checked at `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core main freshly checked at `bcbda4435534a296c707a1daa250813d692f68e1`.
- Core contracts were inspected at the actual Modules dependency pin `41bdfffa6e70228278b4abc758b7f81a12672f35`, not substituted with main.
- `SOURCES.json`: 17 exact source blobs.
- Candidate files only: `model/model-pack/src/adapters/anthropic.rs` and `model/model-pack/src/adapters/openai/stream.rs`.
- Patch: `stream-state-and-delta.patch`.

## 1. State ownership

Before the change, Anthropic stream_response creates one Arc containing one Mutex containing AnthropicStreamState. That Arc is never cloned or exposed. The returned stream alone calls translate under a lock.

The candidate uses a directly owned mutable AnthropicStreamState. It deliberately leaves default construction before stream! and before SSE stream construction, at the original point. This preserves eager creation of the canonical message ID; moving construction inside the generator would be a separate timing change and is not proposed.

translate returns an owned Vec<ModelStreamEvent>. Its mutable borrow ends before any events are yielded. The pinned ModelEventStream contract requires Send, not Sync. The state consists of owned strings, vectors, JSON values, its message ID, counters and the owned DSML filter. Source inspection found no shared reader/writer, callback, spawned task, or reference whose synchronization is being removed.

The event loop, terminal detection, error handling, final response construction and parser implementation are unchanged. There is no existing contention or deadlock claim. A mutex-poisoning branch disappears because the lock itself disappears, not because an error is swallowed.

Source-visible work removed: one explicit Arc allocation site, the Mutex wrapper, and one lock/unwrap site reached per successfully decoded SSE event. This is not a measured throughput, latency, allocation-byte, RSS or PSS improvement. In particular, state moves into the generator's ownership rather than vanishing; the generator representation can change.

## 2. Identical tool-delta branches

OpenAI's function_call_arguments.delta and custom_tool_call_input.delta branches have exactly the same body. An inert byte comparison verified that equality before the edit.

One or-pattern arm now handles both. It preserves:
- call_id selection before item_id, including existing behavior when call_id is present but not a string;
- delta string extraction;
- suppression when the call ID or delta is empty;
- ToolCallDelta with name=None and the same argument delta;
- prior item-ID/call-ID mapping in OpenAiStreamState;
- event ordering, terminal completion and failure handling.

The separate response.completed branch in translate_non_message_event is intentionally left untouched. No dead-code claim based on an incomplete call-site search is used to enlarge this patch.

## Measured source reduction

| File | Before | After | Raw-line delta |
|---|---:|---:|---:|
| anthropic.rs | 287 | 284 | −3 |
| openai/stream.rs | 183 | 162 | −21 |
| Total | 470 | 446 | **−24** |

Nonblank lines: 438 → 414, also −24. Both complete changed files are counted. No helper/new-file costs are hidden; there are no added source files.

The duplicated OpenAI body goes from two copies to one. Anthropic state Arc, Mutex and lock sites each go from one to zero. Those are static source counts, not execution measurements.

## Independent review and checks

`STREAM-OWNERSHIP-REVIEW.md` independently reviewed the exact before/after delta, the pinned Send contract, eager state construction, owned translate output, branch equality, counts and hashes. No source-level semantic blocker was found.

`APPLY-CHECK.json` records successful git apply --check with whitespace errors enabled and application into a separate inert source copy. The resulting two files are byte-identical to the reviewed candidate files. Before/after snapshots are not republished; exact source references and output hashes allow reconstruction. This establishes textual patch applicability only.

Patch SHA256:
`6b21e17767502f83f68b3f8c542412a9836811bf66f15da46170d72b7a09ac14`

## Deduplication and limits

PR106 and PR107 concern workflow sampling and workflow JSON wrappers. This candidate changes model SSE adapter files instead. The published top-level report corpus was searched for this state-ownership and duplicate-delta proposal; no matching proposal was found. This is bounded dedup, not a re-review of every historical artifact.

Earlier model error classification, argument completeness, media and stream-recovery findings are not counted again. This patch does not claim to fix them. Authentication, transport policy, parser defaults and provider-specific semantics were not changed.

**Rust/compiler, formatter, clippy, project scripts, tests, fixtures, providers, application runtime and dependencies were not run or installed.** Existing tests were read, not passed. There is no production-ready or merge-readiness claim.

Before production use, the model-pack scope needs its normal compile/format/test gate, including streamed text/reasoning/tool responses, empty and malformed delta fields, both delta event variants, terminal/error/EOF behavior, and stream drop. These remain unexecuted validation requirements.

Publication recheck: upstream refs still match the stated SHAs; text-only `git apply --check --whitespace=error` repeated successfully. This repository carries proposal documentation, not production integration.
