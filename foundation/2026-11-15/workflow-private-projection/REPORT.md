# Private phase identity: known steering follow-up

## Status

**Source-only, uncompiled candidate. Not a new finding and not a verified runtime fix.**

This follows the existing [PR85 workflow-steering report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/15179849f47731f405dfc2b41f2e67b0f58915e2/research/proteus-continuous-audit-2026-11-13/evidence/workflow-steering/REPORT.md). That report recorded 15 historical fixture runs on older Core/Modules revisions: six failures and nine successful controls. Those runs were not repeated here, and their results do not validate this patch.

Fresh refs checked:
- Modules: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules' pinned Core/contracts: `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Delivery repository: `15179849f47731f405dfc2b41f2e67b0f58915e2`, including #152.

No upstream checkout, live session, provider, external fixture, runtime, installer or user data was changed or exercised. All edits are isolated source copies.

## Common invariant, not another special-case anchor rule

A phase response omitted from persistent workflow history must not continue to advertise its provider response identity as if it were that durable record.

The existing terminal plan branch already changes its copied message ID and every part ID, marks parts Runtime/Request, and retains the source message ID in metadata. The terminal execute draft is also omitted from persistence, but currently retains the provider's message/part identities. See [current plan/execute code](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/workflow/coding-workflow/src/plan_execute_review.rs#L101-L205).

The candidate extracts the existing conversion into one local helper and calls it on exactly the newly appended terminal-plan or terminal-draft suffix. It does not add a phase framework, a new public DTO, a new dependency or a Core exception:
- Every projected message and part gets a fresh identity.
- Every existing part becomes Runtime/Request; payload, part ordering, message ordering, provider phase, name and other message fields are preserved.
- Object metadata is preserved except the reserved source-marker value is replaced. Null becomes an object. Other JSON values are retained under `previous_metadata`, matching the existing metadata convention.
- Plan retains its existing workflow tags. Execute receives no new workflow-phase tag.
- Tool-bearing plan/execute responses and final review retain their canonical identities and persistence path.
- Response validation, tool execution, usage counts, finish reasons, checkpoint order and Core weaving/validation are unchanged.

### Why identity matters for the known failure

[Core request weaving](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/runtime/steering/weave.rs#L13-L35) finds an old response anchor by message ID. When the delivery message is absent from a subsequent request and its old anchor is no longer present, it appends the delivery and sets `awaiting_anchor`. [The next response](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/runtime/steering.rs#L444-L490) supplies a new anchor. Merely changing part scope while retaining the old message ID would not activate that reanchoring path.

For the recorded terminal-draft scenario, making the draft a distinct projection removes the omitted durable anchor from the review request and permits the existing Core path to anchor to the review response. This is source reasoning, not a new end-to-end success result. Both relevant Core files are byte-identical at current Core and the Modules dependency pin. No broader steering-delivery guarantee is claimed, including cases where the delivery message is already present.

## Deliberate limitation: empty-part messages

The pinned response validator rejects an empty message vector but permits an assistant message with zero parts. Both existing workflow ephemeral predicates require nonempty parts whose scopes are all Request.

Consequently, this helper changes an empty message's identity and metadata but cannot make it request-only through a part scope that does not exist. A canonical ACK may drop it; compaction rebuild may include it in persistence. **The non-persistence/retention guarantee is limited to nonempty-part projections. Empty-part lifecycle handling remains open.**

This candidate neither adds fabricated content nor modifies shared classification or Core validation. It is not a universal resolution of all phase/history cases. Compaction can still intentionally remove/change projected content under its existing contract.

## Size and cost

Production change: **+37/-17 lines**, net +20, in one existing file. One helper now owns the plan/draft identity-and-scope policy instead of two phase paths with inconsistent behavior. This is a semantic consolidation, not a LOC reduction claim.

The execute terminal response now incurs O(messages + parts) work, new message/part IDs, and small source-marker metadata allocations. Non-object metadata is moved into the wrapper. No additional payload clone, global cache, retained index or cross-request state is introduced; existing response-to-model copying remains. Plan traversal changes from reverse to forward mutation without changing message/part order. No runtime latency, memory or performance measurement was made.

## Proposed tests, NOT COMPILED / NOT RUN

Three tests in a separate 210-line test module use the actual workflow and existing FakeHost:
1. Ordered two-message plan and draft, six total parts: fresh identities, Runtime/Request scope, payload and provider phase preservation, final-only output. Directly calls the existing rebuild classifier to check exclusion of these nonempty projections.
2. Six draft metadata shapes: null, object, string, array, number and boolean, including overwrite of the reserved source marker.
3. Tool-bearing plan/execute responses remain canonical and durable; terminal draft is projected; final review remains canonical.

The seven existing plan/execute/review tests are unchanged. Their historical success is not a run of this candidate.

**Test boundaries:** default FakeHost acknowledgements have `revision: None`. These three proposed tests do not exercise canonical ACK merge/replacement, an executed compaction, Core steering weaving, cold resume, or a real provider. The existing private-plan ACK test remains unchanged and also was not run.

Rust, Cargo and rustfmt are absent. Python 3.12.14 and system `patch` were used only for source hashing and text operations, not as a behavioral substitute.

## Checks actually performed

- Verified **28 source blobs** against pinned Git tree identities: 17 Modules files, two current Core files, four pinned Core/contracts files, and five published reports/patches. See `SOURCES.json`.
- Candidate patch applied with zero fuzz to the copied baseline; all three target files matched the candidate. Reverse application restored all copied baseline files and removed the new test file.
- Published #106, #107 and #109 patches composed with this patch in both orders:
  - #106, #107, #109, candidate;
  - candidate, #109, #107, #106.
- All applications used zero fuzz; some hunk line offsets were necessary. The resulting **nine target files** were byte-identical. This is not whole-directory or compiled/runtime equivalence.
- Independent design and exact source review accepted the bounded proposal, with the limitations above. See `REVIEW.md`.

This does not test the complete candidate stack. #109 concerns runtime instruction propagation, not private phase identity. #106 sampling consolidation changes this same workflow file but leaves the response-to-model/history decisions in place; the helper composes textually with that structure. #107 changes the JSON workflow wrapper. #108/#110/#111/#117 provider/terminal proposals are separate work and are not declared verified by these checks. #118 completion/delivery and prepared-request accounting remain open. #152 is unrelated Files state work.

## Remaining validation before claiming a fix

With the pinned Rust toolchain/dependencies available:
- Run the documented scoped workflow unit target, including the three new tests.
- Build the affected workflow module through the project workflow.
- Re-run the existing steering fixture on the candidate for both plan- and execute-time delivery, plus no-steering and intervening-tool controls. Verify delivery order, no duplicates, normal final checkpoint, and warm/cold projection agreement.
- Cover canonical ACK replacement, actual compaction, and the explicitly unresolved empty-part edge separately.
- Run appropriate integration gates before an upstream deployment claim.

Patch SHA-256: `76b313b4795a2d408e46cdc7293bd20f1afcd39a68bd119db60b827788cb4605`.

