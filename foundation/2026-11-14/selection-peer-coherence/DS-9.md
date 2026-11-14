# DS9: session model selectors can combine different published snapshots

Status: source-derived P3 presentation/coherence candidate, independently source-reviewed. No Rust, project tests, provider process, HTTP/ACP client or GUI was run. No production changes. Base: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89; tree `00a3c04a70d7927d1688ea155142025f596a2874`. Later upstream changes require revalidation.

## Contract and affected path

`docs/guides/runtime-and-events.md:154–169` describes ACP model/reasoning selectors as the same provider-owned catalog and runtime settings used by HTTP/stdio. Hidden models are included only when selected, and changing model updates its reasoning choices. The model selector is a `{value, options}` projection of an active model and its provider's catalog, not a cross-provider aggregation.

`app_server/model_selection.rs:23–37` samples that projection in separate steps:

1. `runtime.model_ref().await`;
2. `runtime.reasoning().await`;
3. `self.config.read().await.clone()`;
4. `runtime.model_catalog().await`.

Each read can belong to a different publication. In particular, `core/runtime/settings.rs:30–31` captures the catalog's registry only at step 4. There is no shared snapshot or cross-read generation check in this helper. Runtime publication itself installs registry and model_ref together under `execution_state.write` (`runtime/reload.rs:73–88`), so this is a read-side composition problem rather than partial runtime publication.

`selection_summary` (`model_selection.rs:55–75`) finds efforts by the previously sampled active model and assigns every catalog entry the previously sampled active provider. `session_settings::render` (`session_settings.rs:83–98`) independently emits active.model as the selected value and filtered catalog entries as options. `AppServerHandle::session_settings` is public and uses this helper (`127–134`). ACP `settings::options` serializes these values (`acp/settings.rs:10–37`); it is not merely dead diagnostic code.

## Minimal successful interleaving

Use two ordinary valid publications with deliberately distinct identifiers:

- A: active `provider-a/model-a`, catalog contains visible `model-a`, valid effort `high`.
- B: active `provider-b/model-b`, catalog contains visible `model-b`, valid effort `low`.

Start `session_settings` under A. Let it sample active model, reasoning and config from A, then pause before step 4. Complete an ordinary profile publication B. Resume step 4: it gets B's registry and successful catalog. The resulting model selector has:

```text
value = model-a
options = [model-b]
```

Neither coherent publication produces that pair. The internal `ModelOption.provider` is also A even though the catalog came from B, but the generic ACP select DTO does not expose that provider field, so public symptom should be described as mixed value/options, not a visible wrong provider badge.

With disjoint catalogs the reasoning selector can disappear because the new catalog has no entry for the stale active model. This is a consequence of the same cause, not a separate finding. A hidden new active model could be filtered against the stale selection; no additional finding is counted for that variant.

This does not require a failed catalog, process crash, cancellation, disk corruption or changed credentials. It does require a concurrent publication in the read interval. No scheduling frequency is known. A fully old, internally coherent response after slow catalog discovery would not be this defect.

## Scope controls

- `config_summary_with_catalog` already avoids this mixing (`config_summary.rs:158–175`). It captures `configuration_view`, obtains config from that snapshot's assembly, and queries that same snapshot's registry. Do not claim all `/config` responses are affected.
- `model_quota` has its own epoch-change check (`runtime/settings.rs:20–27`). This report is not about quota freshness.
- Actual `set_model_name_with_commit` holds reload_lock and validates against its captured registry (`runtime/settings.rs:39–94`); reasoning updates also revalidate. No wrong-provider model invocation, invalid durable selection, or incorrect paid model call has been established.
- `set_session_setting` uses the affected projection as a preflight list but delegates model/reasoning changes to those validating setters. A malformed/stale visible choice may be rejected; do not elevate the read race into a proved unsafe or incorrectly routed mutation.
- ACP per-session prompt reservations do not by themselves freeze the independent profile publication state. No live ACP client manifestation has been tested.
- This finding concerns model/reasoning presentation only. Other kinds of session setting are outside this audit pass.

## Existing coverage and dedup

Read the full ACP `settings/tests.rs` and HTTP `tests/config_loading.rs`, plus the model-selection parts of HTTP `tests/commands.rs` and external-catalog integration in `tests/model_process.rs:396–466`. These check catalog-driven visible/hidden models, effort values, rejection of invalid metadata, and local config availability during blocked discovery. They do not demonstrate the step-1/step-4 mixed-publication schedule. This is bounded source coverage, not a missing-test claim across the entire repository and not a test run.

Full targeted published reports `settings-lifecycle`, `profile-recovery`, `acp-cli` and the relevant profile-runtime report were checked. Those cover binding invalidation across hot/cold lifecycle, watcher baselines/overlays, config history and launch-time services. They do not match this read-side assembly of model selectors. In particular, the old rejected hypothesis about selection persistence using stale AppServer.config is not revived: persistence already takes config from its locked runtime assembly. PR84 extracted text was searched for selection/catalog/snapshot terms; dedup remains targeted, not all-report exhaustive.

## Proposed regression, not run

Add a deterministic test-only reached/release gate immediately after active/reasoning/config are sampled and before registry/catalog lookup in this helper. Start under A, wait for reached, publish B through the normal app-server profile path, then release. Assert returned model tuple equals a coherent A or B snapshot, never `value=model-a/options=[model-b]`. Read again after completion and expect B. Include a no-publication control.

An existing fixture's `catalog_wait` barrier occurs too late: once catalog dispatch begins, `runtime.model_catalog` has already captured its registry. Blocking that lookup and reloading afterward normally yields a coherent old catalog. It does not deterministically force this particular split. Avoid sleeps or treating `Poll::Pending` alone as proof of the intended phase.

The separate abstract Python model (not included in this publication) represents only the composition of two valid snapshots. It is not extracted Rust, a Tokio schedule, a process integration test, or proof of frequency.

## DRY improvement

Reuse the coherent path that already exists: capture `runtime.configuration_view()` once, derive config from `snapshot.assembly_plan.config()`, and fetch catalog from `snapshot.registry`. Share that small projection helper with `config_summary_with_catalog` and the standalone session-selector path instead of maintaining two different data-acquisition strategies. Keep network discovery outside the settings write lock so a slow catalog does not block normal local reads or publication. A coherent old snapshot is acceptable; enforcing newest-at-return would be a separate product policy.

No broader state framework, new slot, provider-specific exception or global lock is needed for this read-side correction.

## Pinned source anchors

Core paths below are relative to `crates/proteus-core/src/`; key production files were not changed by delivery PR87–89.

- [app_server/model_selection.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/model_selection.rs#L23-L37)
- [core/runtime/settings.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/settings.rs#L30-L32)
- [app_server/config_summary.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/config_summary.rs#L158-L176)
