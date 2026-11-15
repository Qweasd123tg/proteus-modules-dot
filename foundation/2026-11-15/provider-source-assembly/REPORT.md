# Native provider composition: owned stream state, content and typed outcomes

Status: exact source-only assembly of existing #108, #110-on-108, #112, #113 and #117-on-108/110 proposals. No new production edits, new findings or new tests were introduced. This is not a build, runtime reproduction, full provider integration or production qualification. No upstream repository, dependency pin, live profile, provider or deployment was changed.

## Exact source and alternatives

- Modules main: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Actual Modules Core/contracts pin: `41bdfffa6e70228278b4abc758b7f81a12672f35`, retained unchanged in Cargo.toml/Cargo.lock.
- Separately observed Core main: `bcbda4435534a296c707a1daa250813d692f68e1`. It is not substituted for the actual pin.
- Delivery inputs: `c39118022d615cab5bdd30e56137a4bf9ed51261`.

This follows [PR155's bounded integration plan](https://github.com/Qweasd123tg/proteus-modules-dot/blob/c39118022d615cab5bdd30e56137a4bf9ed51261/docs/integration-plan-2026-11-15.md). Earlier packages already recorded source composition of these proposals. This pass assembles one exact alternative, rechecks selected orders on fresh-verified bytes and independently reviews the combined result. It is not a new claim that the originals always auto-merge.

| Selected input | Published directory under `foundation/2026-11-15/` | Exact filename | Git blob |
|---|---|---|---|
| #108 | `model-stream-ownership` | `stream-state-and-delta.patch` | `eb65bf3169c581bd430dd4ebd45733e1b58ce513` |
| #110-on-108 | `anthropic-failure-propagation` | `anthropic-failure-on-PR108.patch` | `52c79930744d31b3cf029878bf4772ee30083a8d` |
| #112 | `anthropic-start-blocks` | `anthropic-start-blocks.patch` | `e6d96c65c58f8d01d1beefdd86e5449583aac4a7` |
| #113 | `native-tool-image-projection` | `native-tool-image-projection.patch` | `6f27cc860bc823fecc222c00ebf6c155e2a36108` |
| #117-on-108/110 | `context-stop-recovery` | `context-stop-recovery-on-PR108-PR110.patch` | `c0a60006ca3e18ef28bc685627375bbade12eb0d` |

**Dependency chain:** #108 precedes the selected #110 rebase, which precedes the selected #117 rebase. #112 and #113 are complementary and do not supply the error-classification dependency. Three chosen placements are checked below; arbitrary order is not promised.

**Alternative, not an extra layer:** apply `composed-provider.patch` to the unmodified pinned Modules source instead of those five selected patches. Do not apply both. Trees with some originals already applied require a separately checked remaining delta. The standalone `anthropic-failure-classification.patch` and `context-stop-recovery-on-PR110.patch` are excluded alternatives, not extra prerequisites. Their exact blobs were retrieved for identity/reference only. The previously documented standalone #108/#110 context conflict was not newly repaired or silently ignored; the already published rebases were used verbatim.

**#111 is excluded.** No Core source, contracts, manifest, lockfile, wire version, public DTO or consumer dependency is changed. The actual pinned default direct Rust `Model::complete` still ignores canonical `Ok(Error)` events and can end in its generic missing-response error. This bundle does not claim typed failure preservation through that inherited direct method. A separately reviewed #111/pin/consumer integration would be needed for that scope. Merely publishing #111 or observing newer Core main does not update Modules dependencies.

## Combined source invariants

### State and content ownership

#108 leaves `AnthropicStreamState::new(status)` eager, before SSE generator construction, while giving the returned stream direct ownership. `translate` returns owned events before yielding, with no retained state mutex. The same message-ID construction timing is preserved. In OpenAI, the identical function/custom argument-delta bodies share one match arm without changing ID selection or delta ordering.

#112 makes start text and subsequent text deltas use the same DSML filter/buffer/event path. Initial tool input is retained when no nonempty JSON delta exists; nonempty fragments replace that value rather than merge or concatenate it. Malformed or whitespace-only nonempty JSON remains an error, not fallback input. Only `tool_use` termination can make those accumulated calls executable.

#113 keeps the old `text_or_status()` string shape when there are no inline images. With images, that exact legacy text/error projection comes first, followed by actual inline images in image order. OpenAI shares an output builder between function/custom outputs and rejects nested images when its profile disables image input. Anthropic preserves call association, `is_error`, and existing message grouping in both Tool-role and inline-result paths. This is not a new lossless ordering contract for every Text/Json/Image block.

### Status-qualified terminal outcomes

#110 and #117 use existing typed failures locally in the Anthropic adapter, not provider-text parsing in workflow or new retry machinery:

| Input boundary | Selected behavior |
|---|---|
| HTTP400, exact `invalid_request_error` and allowlisted `prompt is too long` message | `ContextWindowExceeded` |
| HTTP529, valid `overloaded_error` envelope/message | `Retryable`, no synthetic delay |
| HTTP200 SSE valid overload event | `Retryable` |
| HTTP200 clean SSE EOF without terminal event | `StreamDisconnected` |
| Successfully decoded HTTP200 context-window stop | `ContextWindowExceeded`, not a completed Response |
| `max_tokens`; missing/unknown stop; admitted non-200 context stop | Prior Length/Unknown/Response semantics, subject to the unchanged earlier HTTP/decoder checks |
| Other/malformed error envelopes, malformed SSE JSON, explicit SSE parser/transport errors | Existing `Other` handling, not blanket retryability |

In nonstream mode, existing HTTP checks and decoding happen before context-stop classification. In streaming mode, the context-stop guard is after private pending-text flush but before Response/tool construction; HTTP200 eligibility is checked before choosing the Error shape. The outer status-based kind gate alone would not preserve the non-200 shape, so both checks remain.

Partial deltas may already have been emitted. Context-stop does not turn partial buffers into `completed_messages`, a Response or executable completed tool calls. Normal successful tool use still parses arguments through the existing path; malformed tool-use JSON is not repaired by the start input. These properties survive the selected text assembly; actual HTTP/event behavior was not executed.

## Deliberate open boundaries and costs

- **Failed-attempt usage accounting remains open.** The selected failure carrier has no usage, and the existing durable projection reads usage from responses. Additional recovery attempts can incur generated usage absent from that projection. Direct raw consumers that formerly accepted Length+usage now see failure for eligible context stop; this is a deliberate terminal-shape change, not evidence that accounting is unchanged everywhere.
- The generic direct `Model::complete` issue above remains. Existing other consumers' source handling does not constitute a runtime integration pass.
- Native tool images do not close OpenCode OTM-1, bridge/attachment transport or other providers' behavior. The bundle does not add base64/MIME/size/count/dimension validation or import attachment caps into `ToolContent::Image`.
- Preserving previously discarded images increases request/wire bytes and owned provider JSON strings. Retaining start input requires an owned Value until replacement/finalization/state disposal. Streaming HTTP400/529 now reads full error bodies as already specified in #110. No new global payload budget is introduced.
- #108 removes one explicit unshared Arc/Mutex/lock path and one duplicated delta body; it is not a measured speed, memory or latency result. The full combined diff is +931/−87 lines across 11 files, including prior tests. Composition itself adds no further implementation reduction or behavior change.
- Existing retry budgets, compactor policy, protocol contracts and provider defaults are unchanged. No claim of universal recovery, all-provider parity or lossless failed responses is made.

## Checks actually performed

`SOURCES.json` records 47 verified blobs: 27 Modules baseline files, 12 Core reference files, and eight published inputs/documents (five selected patches, two excluded alternative patches and the plan). Fresh recursive Git trees were retrieved; cached baseline/reference bytes were rehashed against their exact blobs before use. All 12 selected Core reference files are byte-identical at actual pin and observed main, including the still-unfixed default `Model::complete`. This is bounded file identity, not whole-repository equivalence.

System `patch --batch --fuzz=0 -p1` dry-run and application succeeded for exactly these orders:

1. #108 → #110-on-108 → #112 → #113 → #117-on-108/110.
2. #108 → #110-on-108 → #117-on-108/110 → #113 → #112.
3. #113 → #112 → #108 → #110-on-108 → #117-on-108/110.

All 11 target files are byte-identical. There was no conflict, manual resolution, forced application or fuzz; the tool accepted line offsets. Other permutations and standalone variants were not applied in this pass. Target equality is not whole-directory equality: patch backup artifacts can differ.

The combined patch also dry-runs/applies to another owned baseline copy, produces the same target hashes, and reverse-applies to restore all 27 baseline files and remove three newly added targets. `COMPOSITION.json`, target hashes, literal source checks, dependency metadata and text logs preserve this evidence. These copies are source subsets, not complete buildable checkouts. Python performed only file/hash/diff/source bookkeeping, not a Rust model or behavioral test.

## Tests and acceptance still pending

The source retains 21 new proposed Rust functions: #110 four, #112 six, #113 seven, #117 four. One existing context-stop test is also renamed and updated. `TEST-INVENTORY.json` explicitly separates that rename from new tests. #108 supplies no additional test functions. All are **NOT COMPILED / NOT RUN**; no new tests were added by this assembly pass. Their counts do not represent independent end-to-end coverage or runtime passes.

`rustc`, `cargo` and `rustfmt` are unavailable in the selected PATH. No formatter, compiler, clippy, project scripts, fixtures, application/provider process, provider request, benchmark or full suite ran. Earlier historical results are not transferred to this combined tree. No dependencies were installed.

Before qualification: format/compile the exact combined model-pack source against its chosen actual Core pin; run focused serializer, accumulator and error tests; then use controlled loopback HTTP/SSE checks for both modes, including startup, EOF, terminal/error, unknown-status and malformed controls. Exercise compactor trim/retry with successful-summary and max-token controls, and separately assess durable accounting rather than declaring it closed. Validate native image wire output and supported endpoint acceptance without assuming every compatible backend accepts a documented shape. Any future #111 integration must separately prove the selected dependency and direct Rust consumer behavior.

Independent exact source review is recorded in `REVIEW.md`. Publication would deliver a reviewed source alternative, not installed or tested production code.

Combined patch SHA256: `2cf435eab670b0daae79fc135f1bcf576df1d7aee52d74ee63c43bc84e4790da`.
