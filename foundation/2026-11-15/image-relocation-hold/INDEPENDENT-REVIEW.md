# Independent attachment-relocation contract review

Disposition: HOLD a small implementation patch. The known relocation mismatch is supported by current source, but the apparent local path rewrite crosses durable identity and request-recording contracts. A coherent resolver/materialization solution is possible; its ownership, coverage and recording semantics need selection first. No Rust/runtime/dependency execution or fresh incident reproduction was performed.

## Decisive facts

- ImageStore.admit writes under its root by content digest and canonicalizes the resulting path before constructing ImageRef. ImageRef derives full equality and includes id, name, MIME and PathBuf.
- Resumed runtime history comes from the session store; builder constructs ImageStore at the current session_dir/images. ImageStore.read(id) reads that current root, so bytes can remain available through the runtime image API after relocation.
- The native model-pack image encoder instead reads ImageRef.path directly. It receives no current ImageStore resolver in the shown signature. A moved session can therefore retain its bytes while this consumer still addresses the old absolute location.
- Journal PartIdentity falls back to Exact for ContentPart::Image; matches compares the whole CanonicalPart, including ImageRef.path. Projection validates part stability for both history mutations and ModelRequestRecorded. Rewriting a previously recorded image path under the same part id is not a harmless location update under this contract.
- BoundModel applies shaping/hooks and records the resulting canonical request before calling ModelService.start_prepared. Both prepare_request calls inside apply_before_model occur before that record. Thus a rebase in builder history, BeforeModel or prepare_request is not automatically safe merely because it avoids editing old journal bytes.
- Relocation documentation allows moving a stopped session under a different encoded workspace parent; it does not define an image-location migration event or exempt paths from canonical identity. The images guide says source user files are unnecessary for resume, with bytes owned by the session image store.

## Alternatives and missing choices

1. **Rewrite history/requests under existing ids:** blocked by existing identity checks. Excluding path from equality would change the canonical contract, not just fix lookup. New ids or explicit history migration need a selected semantic record/lineage policy; they should not be fabricated as a tiny workaround.
2. **Transient provider-bound materialization after request recording:** plausible narrow placement, preserving recorded canonical bytes and resolving an execution copy from the current session store. However the resolver must be bound to the right session, reach primary and auxiliary calls, and have explicit behavior for non-session/direct model use and delegated contexts. ModelService currently only shapes and dispatches; a global/cwd-based lookup is not equivalent. This route does not cover workflow/hook consumers before model dispatch, and it makes recorded logical request versus executed materialized reference a deliberate distinction.
3. **Separate logical image identity from transport location:** architecturally clearer for all consumers, but requires a chosen cross-process/materialization contract and compatibility treatment for existing absolute refs. It is broader than a local adapter fallback and should not be introduced without that contract.

The existing id-based ImageStore API is useful groundwork, not proof that every consumer already has the necessary session-scoped access. Model adapter relative-path guessing or trusting the old path first does not establish the intended new-session location semantics. No existing general resolver contract was found in the reviewed sources.

## Scope limits

OpenCode's user-image projection requires inline data even before model dispatch. That separate existing incompatibility is not fixed by a provider-only relocation resolver and was explicitly excluded from OTM-1's tool-result media candidate. Do not merge the two claims. This review concerns attachment identity/location only, not other lifecycle or access behavior.

Source-read boundaries: ImageRef; ImageStore admission/read; builder history/store creation; ModelService and BoundModel request/hook/record/start ordering; journal projection and part identity; model-pack image encoding; image/relocation guides and native attachment projections. Coordinator baseline/ref verification remains provenance; no execution or full consumer inventory is claimed. HOLD is a scope/contract decision, not a statement that relocation support is impossible or that only a large framework can solve it.
