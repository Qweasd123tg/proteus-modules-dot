# Independent pre-patch design review

Verdict: a separate weak, entity-keyed live-recipient index is a meaningful narrow candidate for the known PR85 multiview #2 family. No blocking design objection identified in the inspected functional paths. This is not a new finding, a runtime result, or approval of an unseen patch.

## Why the existing index is insufficient

`runtime_of` intentionally chooses a default by host/package or view-owner/package. `rehost_runtime` overwrites the destination default. The previous runtime can remain strongly owned by existing DeclarativeView entities while no longer being selectable through either default map. `invalidation::runtimes` deduplicates entries it can enumerate but cannot recover an absent live entity. `reload_runtimes` likewise enumerates defaults, and its current loops can visit aliases repeatedly.

Recipient discovery and default selection are different relations. Registering each newly constructed production Runtime under its EntityId before the owned-view early return preserves both categories independently of later default-map replacement. The inspected `mod.rs::runtime` is the production construction site; the visible `documents.rs` direct construction is under cfg(test). The broader construction-site search supplied by the coordinator should remain recorded as separate provenance, not a runtime guarantee.

## Required implementation details

- Keep default lookup, rehost, owner retention and scope pruning unchanged. The new map is not another selection policy.
- Store only a weak entity plus the stable package identity, and prune expired weak entries on insertion. Do not capture strong entities in the global registry. This bounds live ownership impact, not map capacity or dead-entry accumulation between insertions.
- Register before either return path. Package identity must be the same immutable identity used by that Runtime/default registration; it is not a mutable display title or revision.
- Both enumeration consumers should collect upgraded entities into an owned vector before any update/reload callback. Do not retain a global borrow across callbacks, and avoid reading the Runtime itself merely to filter the package while it might already be borrowed. The stored package identity allows that.
- EntityId keys make a runtime appear once despite multiple default aliases. The resulting vector temporarily retains recipients for the duration of fanout; it is not a forever-retention mechanism. Ordering is already HashMap-derived and should not acquire a new promise.
- Keep existing downstream matching/eligibility logic untouched. `documents.rs` also consumes invalidation::runtimes for exact-pair recipient enumeration, so it gains restored recipients but not missing rename-pair generation or prefix semantics. That separate historical #1 remains open.

## Qualification and caveats

This changes the set of recipients intentionally: still-live displaced runtimes must now receive existing invalidation/reload work. Do not claim lower work, no additional renders, or a fixed memory cap. It does not merge runtimes, close old defaults, reconcile selected views, or prove delivery to every visible native surface. PR146's announcement adjustment and PR147's package-local tab state do not establish integration qualification here.

Useful proposed tests should use actual registry/enumeration functions with two live runtime entities for one destination/package; overwrite its default with a rehosted third entity; verify both displaced and selected entities remain discoverable exactly once. Add other-package exclusion, owned-view registration, multiple aliases, expired weak entries/pruning, and default lookup unchanged controls. Separately check the reload recipient collector if it is not shared with invalidation. Direct Runtime::new test fixtures bypass the proposed production registration point and must register deliberately or exercise the real factory: otherwise such fixtures cannot establish production registration coverage. Pure tuple/dedup tests alone would not reproduce the lost-registration invariant.

No Rust, native UI, project tests, synthetic behavioral substitute, or extension execution was performed. Review was limited to functional ownership/enumeration and relevant lifecycle code; no launch, process-authority, or security behavior was investigated.

## Exact source candidate

Locally verified patch SHA256 `e1af3bcc38b3402a9c7ffa96ee307310a15f8da811e986ed7a74f180a21de9b3`.

Production source has no identified blocker: `installed()` provides a static Installed reference, making the stored manifest-id borrow valid; the new registration precedes the owned-view early return; default lookup/rehost bodies remain unchanged. The filter uses stored package identity without borrowing recipient Runtime entities. Collection returns owned upgraded entities before callers update them, releasing the global borrow. Entity-keyed insertion deduplicates aliases and the removed generic targets helper is no longer needed. The retained invalidation-generation test remains in place.

The proposed nested test module path and `super::super::super` imports resolve to the declarative module; descendant access to private registry helpers is plausible. Window/TestAppContext and Workspace::test_empty usage follows neighboring source patterns. Direct construction explicitly registers before adding default mappings, so these are registry-function tests, not production factory coverage. None invokes attach/render/reload. The rehost case checks actual default replacement plus preserved recipients; the owned-view case checks package filtering and both owner categories; the invalid-weak case deliberately substitutes a synthetic invalid handle while the old entity is still owned, so it is not evidence of native GC or last-owner release. The snapshot test verifies owned collection independence, not reentrant callback behavior.

One compile-plausibility issue merits correction before finalizing the test source: this new module glob-imports `gpui_kit::*` and uses bare `#[test]`, whereas neighboring documents.rs tests use `#[::core::prelude::v1::test]` in the GPUI-import context. Without the exact reexport/toolchain qualification, avoid a potential imported test-macro ambiguity by using the same explicit standard test attribute for all six cases. This does not affect the production design. All tests remain NOT COMPILED / NOT RUN; no source review establishes GPUI execution success.

### Revised exact candidate

Final patch SHA256 checked locally: `8174bb6a9eb4e000c4fcef61c13e28845592e22fe17a25e4f5e4f27bfc4a2cc5`. All six new test attributes now explicitly name `::core::prelude::v1::test`; the test-attribute remark above is resolved. The registry comment now correctly scopes automatic registration to recipients created by `runtime()`, rather than all direct constructors. Manual test line wrapping does not change the reviewed assertions. No new source blocker identified; qualification remains source-only, with all Rust tests NOT COMPILED / NOT RUN.

## Final prose acceptance

Locally read and hashed:
- REPORT.md: `914d89cf78daa7ee4f7b5eae7ad519cab6f8676182f7ab8ab084a322b384026f`
- README.md: `0a825caa643adbc51187f3ac90de8fd9795e12a54d4eb0c7790054ccf0e4d3a1`
- CHECKS.md: `db55290f4ba158c0702d6fa9053547eae83d5ccd9d6b4e408126c1e1087c9d65`
- Patch remains `8174bb6a9eb4e000c4fcef61c13e28845592e22fe17a25e4f5e4f27bfc4a2cc5`.

No blocking prose correction identified. The inventory/default-selection distinction, additional weak-index memory and insertion scan, lazy cleanup/capacity limits, temporary strong recipient snapshots, and additional intended work are explicit. Historical issue #1 is not claimed repaired. Ordinary scope subscriptions are correctly distinguished from global recipient enumeration. Source-only #146/#147 compatibility is not represented as tested native integration.

The six proposed tests and retained generation test remain NOT COMPILED / NOT RUN; fixture registration is not production-factory execution and invalid-weak substitution is not object-release timing evidence. The report also disclaims unchanged baseline execution of candidate-specific tests. Source identity/apply/byte-comparison results are coordinator artifact evidence; this final review adds local prose/hash inspection only, with no project or behavioral execution. Final status remains a reviewed uncompiled proposal, not user-visible recovery qualification.
