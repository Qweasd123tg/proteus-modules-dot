# HOLD: model-selection identity is not yet a shared override policy

Bounded source-only follow-up to known PR85 `settings-lifecycle` finding #3. No new finding, production patch, test implementation or runtime reproduction is proposed by this pass. Core remains `bcbda4435534a296c707a1daa250813d692f68e1`; delivery main after PR139 is `51f6fc07316fcca9b315a648013a1303405712fd`.

The known issue remains source-applicable: changing opaque model-module configuration or its component descriptor can preserve the current model override live while its previously saved binding is rejected on cold resume. profile.rs and session_selection.rs are byte-identical to the historical report's versions. That earlier reproduction was NOT RERUN.

## Why not mechanically reuse the binding hash?

Persisted `Selection` version 1 contains one hash binding and one model/reasoning pair. Its binding includes resolved profile path, profile.name, active provider alias, selected ModelConfig, opaque selected model-module configuration and the relevant component descriptions. Selected ModelConfig contains provider, model, stream and reasoning. It does **not** contain ProviderProfileConfig.reasoning_efforts.

Hot publication currently compares model_ref and reasoning defaults separately. The existing documented policy preserves unrelated session overrides and applies the corresponding changed default. Replacing both predicates with `old_binding != new_binding` would impose a materially broader reset, not merely centralize an already shared rule.

Representative current-source matrix, assuming the same configured provider and no new explicit selection after the edit:

| Profile change | Current hot publication | Cold admission of prior saved pair |
|---|---|---|
| Model default only | Replace model; preserve reasoning override | Prior hash differs, discard saved pair |
| Reasoning default only | Preserve model override; replace reasoning | Prior hash differs, discard saved pair |
| Profile name or stream only | Preserve both overrides | Prior hash differs, discard saved pair |
| Selected model route/component description only | Preserve both overrides | Prior hash differs, discard saved pair |
| Declared reasoning_efforts only | Preserve both overrides | Not part of selected ModelConfig binding |

These rows describe the predicates, not newly executed scenarios or new severity claims. The route/component row is the existing known family. The low-level reasoning_reload test treats profile rename as unrelated and preserves an override; it is a control for low-level runtime semantics, not proof of app-server cold-resume behavior.

## Route identity is not capability compatibility

`set_model_name_with_commit` consults the provider catalog and normalizes reasoning effort for an explicitly selected model. `set_reasoning_effort_with_commit` also checks catalog options when available. `restore_model_selection` deliberately avoids a catalog call so a temporary discovery outage cannot erase a durable user choice. Hot publication does not invoke those setter validation flows.

An opaque route change alone does not prove that the chosen model ID or effort became incompatible. Conversely, an unchanged serialized route does not prove that a dynamic provider catalog is unchanged. Declared fallback effort options are handled separately in config_summary; they are not the stored binding's model compatibility test. A shared hash helper would not establish a capability invariant, and querying the catalog on every reload would introduce new failure/availability semantics rather than being a free fix.

## Decision needed before implementation

A safe implementation needs an explicit invalidation matrix distinguishing independent model/reasoning default changes, provider/route identity changes, profile-name/stream changes and capability updates. It must state what happens to explicit user choices and to unknown catalog availability. The persisted single-pair binding and any migration/rebinding behavior then need to match that policy without silently changing old preferences.

The narrow route-only alternative can be implemented mechanically, but doing so now would either repeat a second hand-maintained comparison or introduce an arbitrary reset policy that still disagrees with the other rows. The full-binding alternative would silently erase unrelated overrides. Neither was patched merely to report fewer conditionals.

Recommendation: retain HOLD for mechanical predicate unification. Choose the selection policy first; then share its typed comparison at the live/cold boundary and qualify actual publication, explicit overrides, failed reload, catalog outage and cold resume using current fixtures. This pass does not authorize or design a new generic settings framework.

## Evidence and limits

Nine relevant current source/document files were Git-blob/SHA256 verified. Independent read-only review agrees that the policy distinction blocks a behavior-preserving common-predicate patch. The separate DS-9 snapshot-coherence proposal concerns mixed presentation snapshots, not persisted override invalidation. PR139's MCP schema discovery proposal is also unrelated.

No model catalog, provider API, model, server, tests, compiler or project executable was run. Python was used only for source-file/hash bookkeeping. No runtime incidence, performance gain, automatic preference migration or closure of the known finding is claimed. No upstream files were changed, and no patch was created.
