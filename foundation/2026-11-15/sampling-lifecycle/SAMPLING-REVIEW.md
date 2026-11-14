# Independent source review: sampling lifecycle extraction

## Verdict

No blocking semantic difference identified in the five replaced call sites. The extraction is proportionate: one common sampling lifecycle, while the callers still visibly own phase transitions, response persistence, private projections, tools, output, and usage observations. Recommend retaining this scope rather than expanding it to Codex/project_check or constructing a generic workflow engine.

This is source-review acceptance of an isolated candidate, not a compilation/test/runtime guarantee. No compiler, formatter, tests, project scripts, providers, or dependency installation were run. No production modification or publication was performed by this reviewer.

## Adversarial equivalence checks

- **Preparation and ACK order:** all five sites retain `request_from_state` → `apply_compaction_report(Rebuild)` → on changed, checkpoint → copy ACK-adjusted `turn.model_messages` into the prepared request. The helper does not sample the pre-ACK message snapshot or add an unconditional checkpoint. Unchanged-report accumulation still occurs inside the same scaffold method.
- **Preparation errors and checkpoint rejection:** each operation still propagates its error before sampling. The owning run function still converts that error through the same `turn.failure` path, preserving staged-preparation failure handling. No response is appended by the helper.
- **Forced no-tool request:** single-loop final, final planning round, and review suppress tools only after preparation/ACK, as before. Selected schema budget, preparation inputs and phase-specific dynamic-tool rules therefore remain unchanged. Tools are cleared and ToolChoice None assigned before request event/completion/validation.
- **Builder equivalence:** fresh-read Core `bcbda4435534a296c707a1daa250813d692f68e1`, `crates/proteus-contracts/src/model_standard/canonical_request.rs`, confirms `with_tool_choice` only assigns that field and returns self. Replacing it with direct assignment has no additional builder behavior to preserve. Saved fresh source in `review-evidence/canonical_request.rs`; SOURCES.json now also includes this Core file as entry 12, blob `c91a5d006e1186399ae6d77ee5d25e482485681b`.
- **Planning flag timing:** only the local comparison `plan_round == MAX_PLAN_TOOL_ROUNDS` moves earlier. It has no side effects or mutable dependencies. Do not describe `request_from_state` as pure: it calls selection/context-preparation host operations. Their order has not changed.
- **Events and validation:** request event still precedes completion; complete_model still performs token-usage emission internally; response event still precedes validation. Phase strings and instruction selections match all five original sites. Validation checks the same effective request, including suppressed tools.
- **Usage lifetime:** iterative sites still reset last_usage on changed compaction before ACK and preserve it otherwise. Final single-loop/review now also reset that local on compaction, unlike the originals. No later read exists on either terminal path, including error conversion; LastModelUsage carries ordinary usage data. This is a syntactic state change with no identified externally observable behavior, not a strict claim that every local assignment is identical.
- **Caller-owned semantics:** loop bounds, plan-round counter, finish-reason branching, source-to-private plan identities, draft persistence choice, tool execution/checkpoints, final message selection and output metadata stay in callers. The helper neither records the new response in history nor updates LastModelUsage from response usage, avoiding accidental conflation of these distinct responsibilities.
- **Types/visibility by inspection:** helper uses the same response/error types as the extracted blocks, imports sibling-visible functions, and is registered in lib.rs. No borrowed request/step lifetime escapes in the owned return type. This is inspection only, not a compile result.

## Measured scope

Independently counted raw lines of the four changed/added files with text-only tooling:

| File | Before | After |
|---|---:|---:|
| lib.rs | 92 | 93 |
| single_loop.rs | 176 | 131 |
| plan_execute_review.rs | 277 | 206 |
| sampling.rs | 0 | 71 |
| Total | 545 | 501 |

Net **44 raw lines deleted**, including the new helper and module registration. Coordinator LOC.json also records net 46 nonblank lines deleted; raw counts were independently checked here. This is a real reduction in duplicated source, not a performance, binary-size, or maintenance-cost measurement.

## Nonblocking clarity notes

`disable_tools` now literally names the suppression of tool calling; it does not set a response-format field or guarantee nonempty text. The follow-up rename was checked at the declaration, all five call sites, and the helper field access. Replacing only `disable_tools` back to `force_text` in each of the three affected files reproduces its previously reviewed SHA256 exactly. The `forced_text_round` local and behavior are unchanged. The explicit per-phase struct literals are preferable to hiding phase/history policy for a few more deleted lines.

## Evidence identity

Baseline Modules pin: `c035142558f0fca43e9772fc0e50ca293abf1531`; exact baseline blobs are catalogued in SOURCES.json. Read patch, before/after callers, helper, host/scaffold/validation boundaries and focused preparation test excerpts as source only. Repository heads and the full baseline blob verification were supplied by coordinator, not independently repeated.

Reviewed candidate SHA256:

- lib.rs: `f86c0ed11ce9c1c50abfa2e279d412108927cf22b43351d8a732cfe8ea590273`
- single_loop.rs: `5d583b1c1436868550f66eca99254df2043f0b5ba005b1d49f04f79757101800`
- plan_execute_review.rs: `385c8e0039241d1128f1c7214970b281676554c806c55be1572a68c5870478da`
- sampling.rs: `8de586da3f6b46dbf0e3d861f6f9f14636a0482bcdc41ac77bb775c6d81958d9`

Existing defects or documented workflow limitations are not claimed fixed by this refactor. Regression execution remains unperformed under the source-only constraint.
