# Live UI recipients are not default runtime selection

## Status

**Source-only candidate for the existing PR85 `extension-multiview` issue #2. Not a new finding. NOT COMPILED / NOT RUN.** No production checkout or installed application was changed. No extension process, native UI, external service, or project test was executed.

Pinned Desktop: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
Extensions: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
Delivery/dedup baseline: `41e13efed3e2631322da8deca2c844416f415e3f`, including the uncompiled proposals #146 and #147.

The earlier report reproduced the registry logic using exact production function bodies with Rc/Weak substitutes on older revisions. Its observations are historical evidence, not a current native reproduction or evidence that this patch runs. The historical report has Git blob identity `2bd7d28d4ae40589efafa4ff2d3e24a554abd795` in the delivery repository; it is not duplicated here.

## The common invariant

A host-to-runtime index answers **which runtime a newly opened surface should join**. It cannot also be the complete inventory of **which existing runtime entities remain alive**.

Current `runtime_of` selects by host/package or owned-view/package. `rehost_runtime` intentionally replaces the destination host's default with the moved runtime. Existing views may still strongly retain the displaced runtime. However, both package invalidation/retarget enumeration and package reload enumerate the default-selection maps, so a displaced live entity with no remaining default alias is absent. Deduplicating those maps cannot restore a missing entity.

Source chain on the pinned Desktop:

- [`mod.rs`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/ui/extensions/declarative/mod.rs): default maps/lookup, factory registration, destination overwrite, reload enumeration.
- [`view.rs`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/ui/extensions/declarative/view.rs): retained runtime entity and view rehost.
- [`invalidation.rs`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/ui/extensions/declarative/runtime/invalidation.rs): recipients drawn from the two default maps, then deduplicated.
- [`documents.rs`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/ui/extensions/declarative/runtime/documents.rs): exact-pair retarget uses the same recipient collector and separately checks document/session/connection matches.
- [`scopes.rs`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/ui/extensions/declarative/runtime/scopes.rs): deferred rehost uses the same runtime entity; attached route-generation check remains in place.

These source observations do not establish the incidence or visible effect of native drag-and-drop, settings changes, or reload in the current release.

## Candidate

1. Keep `Runtimes`, `ViewRuntimes`, `runtime_of`, rehost overwrite, and strong owner retention unchanged.
2. Add `LiveRuntimes`, a separate `EntityId -> (stable package id, WeakEntity<Runtime>)` index. Register in `runtime()` immediately after construction, before either ownership-specific return path.
3. Use one `live_runtimes` collector for package-local fanout and all-package reload. It filters using the recorded package id, upgrades weak references, and returns an owned vector before callbacks. It does not read the recipient Runtime merely to select it.
4. Remove the old generic tuple-dedup helper, both HashSet dedup passes, and duplicated default-map traversal. Entity identity provides uniqueness directly.

The factory is the inspected production construction point. GitHub code search for `Runtime::new` returned this factory plus test-only uses in `runtime/commands.rs`, `runtime/documents.rs`, and `content/tests.rs`; the latter's parent declares it under `cfg(test)`. This is source/search coverage, not a dynamic creation-site proof. Future production constructors must register too. The new test fixtures deliberately call the registration helper because they bypass the production factory.

Production-only diff: **+33 / -67 lines, net -34**, across two files. `MEASUREMENTS.json` counts production text before the first `cfg(test)` boundary. This is a text measurement, not a latency/RSS/CPU result. The full patch is larger because it replaces the old tuple-only test with six proposed registry tests in a new 175-line test-only module.

## Ownership, cleanup, and costs

- The additional index owns one entity key, borrowed static package id and weak reference per registered runtime entry, plus HashMap storage. Existing default indices remain. It is additional indexing, not a claim of lower retained memory.
- Registration prunes entries whose weak reference cannot upgrade. Enumeration skips expired entries without mutating the registry. Live displaced entities are intentionally retained in the inventory while some existing owner keeps them alive.
- There is no new strong global owner or eager close/reset. Recipient vectors temporarily retain selected entities during fanout, as the previous collection paths already did.
- Cleanup is lazy on the next registration. Dead entries may remain between registrations; removals do not necessarily shrink capacity. No hard entry/byte cap or zero-cost guarantee is claimed. Each registration adds a scan of this index.
- Previously omitted live recipients now receive existing invalidation/retarget/reload work. This can increase correct work and render/reload activity. No no-extra-renders, scheduling, delivery-ACK, or end-to-end refresh guarantee is claimed.
- HashMap-derived callback order remains unspecified. The change promises neither a new order nor simultaneous callbacks.

## Composition and exclusions

The proposal does not alter how a host chooses a runtime, merge runtime instances, migrate existing view state, or expand document matching. It only changes recipient enumeration to include registered live entities once.

Historical multiview #1 remains open: if Files never emits the missing rename pair for another runtime's descendant document, a better recipient inventory cannot invent it. Folder-prefix semantics and document mode migration are not implemented here.

#146 changes initial context/navigation announcement in `scopes.rs`; it does not repair default-map enumeration. Existing scope subscriptions can still deliver ordinary host/navigation events without this global registry, so this report does not claim that all navigation previously stopped. The candidate has no textual overlap with #146, but native deferred rehost/bootstrap ordering and restart composition have not been run.

#147 changes Git package-local per-view selection. It neither creates nor replaces this Desktop inventory. No composition runtime test was run for #146/#147 or other candidates.

This pass did not investigate process-security, authorization, launch, sandbox, cancellation, or other excluded areas. Existing downstream eligibility checks and scope matching remain unchanged.

## Proposed verification, not executed

Six tests use real registry/collector/default-lookup/rehost functions with GPUI entities and inert, directly constructed Runtime fixtures. They do not attach surfaces or call render/reload:

1. Destination overwrite retains both selected and displaced live recipients, default lookup remains moved runtime, repeated aliases stay unique; all-package collector sees the same pair.
2. Production, Settings, Preview, other-package and absent-package controls preserve both lookup relations and fanout filtering.
3. Re-registration does not duplicate recipients or change either default choice.
4. A deliberately invalid weak reference is skipped before cleanup and pruned during later registration without deleting live entries. This is **not** native object-release/GC timing coverage.
5. A recipient snapshot can coexist with subsequent registration; the next collection sees new recipients.
6. Empty enumeration neither requires nor creates a registry global.

The existing unmounted-invalidation generation test remains. The removed tuple-only test's package/alias behavior is represented in the proposed registry controls.

All six new tests and the existing test are **NOT COMPILED / NOT RUN**. There is no current baseline-red/candidate-green observation. The new tests reference candidate helpers, so they are not a baseline executable regression unchanged.

Before adoption: compile/run focused registry and existing invalidation/document/content tests; check actual factory wiring and entity-release cleanup, displaced native views and deferred rehost, downstream invalidate/retarget effects and reload, and #146/#147 composition. The tests do not simulate a completed install/update, native drag gesture, live server rename, or renderer response.

## Actual checks

- 11 source/doc snapshots match exact pinned Desktop Git blobs. Historical report blob matches delivery tree.
- Independent design and exact-patch review found no production source blocker. The test macro qualification concern was corrected; final reviewed patch SHA-256 is `8174bb6a9eb4e000c4fcef61c13e28845592e22fe17a25e4f5e4f27bfc4a2cc5`.
- `git apply --check --whitespace=error-all`, strict `patch --batch --fuzz=0 -p1`, reverse apply check, and byte-for-byte candidate/application comparisons succeeded in an isolated copy.
- Only text/diff/hash bookkeeping was executed. `cargo` and `rustc` are absent from PATH; no installation was attempted. No Rust formatting, compilation, project tests, Python behavioral model, or native UI test was substituted for the missing toolchain.

This is a reviewed proposal, not production qualification or proof of successful user-visible recovery.
