# Independent design review: file-include model persistence

Source review on pinned Core cdf4aa5c. Rust not run. Current proposal is not yet production-qualified.

## Confirmed issue

The ordinary file include merge retains inherited keys. Current persistence decides named-versus-legacy spelling using only the local wrapper, whereas AppConfig has normalized away the source spelling. A switch over a legacy included selection may introduce model beside active_provider; unrelated save over named include may introduce active_provider beside model. This differs from managed directory overlays and inline-role inheritance.

## Blocking issues before claiming repair

1. Selection and catalogue spelling are independent axes. The loader allows model + providers and active_provider + models, while rejecting both alternatives of either axis. A single `named` boolean inferred from any of the four keys is not sufficient provenance for all accepted input shapes.
2. Named catalogue values also have spelling provenance: flat effort/summary/budget_tokens normalize into reasoning fields. Recursively merging serialized normalized presets over an included flat field can produce duplicate flat and nested reasoning fields rejected by named_presets. Preserving only catalogue key does not fix catalogue edits.
3. Proposed native test currently converts source() to legacy providers without removing its flat effort fields. ProviderProfileConfig denies unknown fields and has only reasoning, not effort; the legacy test fixture would fail before Save. Fix fixture before treating its failure as a regression.
4. Removing a local choice cannot clear an inherited choice with ordinary additive includes. Do not claim selection clearing works merely because local key deletion succeeds.

## Bounded implementation recommendation

Read source-level merged choice provenance with the existing include resolver before normalization, without changing global merge semantics. For ordinary wrappers and only selection/unrelated changes, preserve the inherited selection spelling. Do not write an inherited choice for unrelated changes. Preserve managed overlay and inline-role behavior unless separately qualified. Keep uncertain catalogue/clear operations explicitly out of this narrow fix or reject them before writing with a precise unsupported-operation error; never silently claim saved state matches the requested runtime config.

A broader shared candidate-source validation layer could prevent invalid output, but must evaluate candidate bytes within the original include context before replacing the file. A post-rename reload is not transactional protection. This needs tests and is not automatically a smaller change than the bounded fix.

Required native coverage: both formats; both spelling pairs; valid mixed pairs; unchanged edit; switch; inherited clear; catalogue edit with flat reasoning fields; preserved base bytes; unchanged directory-overlay and inline-role existing tests. Not all of these must be implemented in the narrow scope, but limitations should be explicit.

## Revised bounded candidate review

Reviewed production SHA256 `ae75247b90b399fb72a0745e976f334f8e22b264ef0ad30cb8ecc4296d0b61df` and test SHA256 `b516986af47803f9c179cd05b7e6491fa994d122a405240c15e6f205906ba490`.

The revised code handles only file wrappers with includes and no local catalogue. It queries merged raw choice spelling through the existing resolver. It keeps the guarded path after a previous save materializes a local choice, addressing the repeat-save hole identified during review. Both writers share the same provenance query and rejection rules; unrelated saves leave inherited choice unmaterialized. Changed choice uses its existing key, independently of catalogue spelling. Catalogue edits and clearing choice are rejected before writing. Inline selection and managed overlay paths are excluded, leaving their existing behavior unchanged.

The final native fixture no longer carries invalid flat effort into legacy providers. Its one test method covers 2 formats × 2 choice spellings × 2 catalogue spellings, repeated main/budget/main saves, then clear/catalogue rejection and byte preservation. It is source only and NOT RUN.

No remaining blocking source defect found in this bounded scope. Independently applied both patches to exact source copies, compared all 3 candidate files byte-for-byte, reversed patches and verified original byte restoration. This is not compilation or runtime qualification.

Material behavior limit: this is a conservative restriction, not a globally behavior-preserving refactor. Any include wrapper without local catalogue but with its own local choice is also guarded, even if its includes do not actually supply that choice. Clearing such a local choice is rejected too. Document that boundary; do not claim every previously valid edit remains supported. Broader source/catalogue edits, inline include interactions, concurrent source mutation, and a transactional candidate reload remain outside the fix.

## Final revision (supersedes preceding candidate verdict)

Production SHA256 now `6bdf41e0bd31fd37d7e72940e6764a5d8e1e28515c06852dde4ff9d2d0a0e578`; native test remains `b516986af47803f9c179cd05b7e6491fa994d122a405240c15e6f205906ba490`.

The helper now merges only actual include contributions using the existing resolve/load/merge functions and excludes the local wrapper from the choice-key decision. This removes the previously described local-only-choice restriction when includes contain no selection: that path returns None and retains existing persistence behavior. A materialized local override over a genuinely inherited choice remains guarded after repeated saves. Merge order is unchanged; existing recursive loader retains cycle/error handling. Full baseline loading still precedes this query, so an already ambiguous source is not silently accepted by this helper.

No blocking source defect found in the final bounded implementation. Independently repeated combined forward application, exact equality of all three candidate files, reverse application and exact baseline restoration. Results in INDEPENDENT-FINAL-CHECKS.json. Native compilation/tests/formatting remain NOT RUN.

Scope still matters: inherited selection clearing and inherited catalogue changes are rejected; local catalogues, inline-role selections and managed overlay paths retain their previous handling and are not claimed fixed. Additional filesystem reads do not establish a race-free snapshot or transaction. The native matrix does not yet cover the local-only-choice/unrelated-include negative-scope case, though the branch is directly inspectable; adding that case would strengthen future runtime qualification.
