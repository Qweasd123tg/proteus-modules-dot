# File-include model selection persistence: recovered audit

Base: Proteus-harness/Proteus-core cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d. Main confirmed through connector on 2026-11-16. No upstream or remote changes.

## Source-confirmed failure chain

1. A file `agent.toml`/`agent.json` includes a base containing either `model`+`models` or legacy `active_provider`+`providers`.
2. Load merges the included base into the wrapper, then normalizes model source syntax to runtime AppConfig. The wrapper's local source has neither choice nor catalogue key.
3. persistence.rs decides source spelling from the local document plus changed runtime values. With an unrelated edit, it writes `active_provider` for a non-inline wrapper. With a changed selection, it writes `model`.
4. The ordinary file-include loader recursively merges keys; unlike managed directory overlays, it does not remove the inherited alternative choice key.
5. Named-base/unrelated-save and legacy-base/selection-switch therefore produce both choice keys. models.rs explicitly rejects this pair. Base source bytes are not necessarily damaged, but the saved wrapper is no longer loadable.

The serialization representation has lost the original choice provenance. This is a semantic persistence issue, not an atomic filesystem-write failure. The existing directory-overlay test does not cover it because directory-overlay loading expressly removes both choice keys before merging. Existing inline-child tests also do not cover a plain file include wrapper.

## What was actually checked

- Recovered authored Python branch controls rerun and matched the existing JSON byte-for-byte: eight format/source/edit combinations, four modeled rejections. This is NOT the Rust loader or Save execution.
- Four key local source files match exact Git blob identities in the pinned remote tree.
- Added a proposed native regression method to the existing model_names test file, not a new suite. It exercises eight source-format/spelling setups with real AppConfig load/persist/reload when run, and checks unchanged base bytes and unfrozen catalogues.
- Native test patch passes `git apply --check`. Rust/Cargo unavailable; compilation, native test, runtime and CI NOT RUN. No claim the proposed test compiles or has failed on the baseline yet.

## Repair direction and constraints

First qualify the native regression on the exact base. Preserve the original choice spelling through the merged source/provenance boundary, and use one shared decision for JSON and TOML persistence. Avoid changing ordinary additive includes globally or making directory-overlay semantics apply to every wrapper. An unrelated edit should not materialize an inherited choice unnecessarily; an intentional switch must override the inherited spelling rather than introduce its alternate. Catalogue edits (`models` versus `providers`) are an adjacent required case before calling the family fixed.

A write-time loadability check can be defense in depth only if it validates the candidate in the same include context before replacing the saved file. Simply reloading after rename would detect corruption after publication and would not establish transactional safety. The follow-up below includes a bounded candidate for selection edits; broader catalogue repair remains deferred.

## Bounded production candidate (follow-up)

`file-include-model-choice.patch` adds one crate-private source query using the existing include resolver and merge functions. It inspects only included contributions before model normalization, returning their exact choice key. The JSON/TOML writers share this decision. For a plain include wrapper without a locally owned catalogue:

- Unrelated saves preserve the absent inherited choice rather than freeze it locally.
- Selection edits write the inherited spelling, including subsequent edits after the local selection has materialized.
- Include files and catalogue bytes stay untouched.
- Clearing an inherited selection and editing its catalogue are explicitly rejected before atomic_write. These are deliberate safety restrictions on this bounded path, not completed support for such operations. Local-only choices with unrelated includes are not classified as inherited.

Inline-role sources, managed directory overlays, and locally owned catalogues follow their existing paths. Global additive merge semantics are unchanged. This does not repair all possible mixed-format/catalogue edits, nor add transactional snapshot validation against concurrently changing includes. It does not change the provider or model contract.

The proposed regression now covers 8 independent format/choice-key/catalogue-key setups, with repeated main→budget→main save/reload and two refusal checks preserving file bytes. One existing-suite method is added. These are proposed native checks, not executed counts.

The final combined production/test candidates passed exact-byte forward/reverse application with zero fuzz/offset, using the declared base. Independent source review is recorded separately with hashes; native tests remain NOT RUN. This is worthwhile to preserve as a source-only repair candidate because it prevents a concrete reload failure, but must not be presented as deployable or a complete model persistence redesign without compilation and native regression execution.
