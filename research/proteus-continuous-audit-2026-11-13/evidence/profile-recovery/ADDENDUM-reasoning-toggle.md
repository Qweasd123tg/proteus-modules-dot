# Third finding: model switch → reasoning toggle bypasses the selected model's catalog

Core `89997df995df7c39b713e16aba216ecb19c8f497`, 2026-11-13. Local test-only audit. No production changes or publication.

## P2, confirmed at runtime and persistence callback boundary

A valid configuration baseline selects model A with reasoning effort `xhigh`. The provider's valid authoritative catalog says A supports `xhigh` but B supports only `low`, default `low`.

1. `set_model_name("model-b")` correctly changes reasoning to `low`.
2. Direct `set_reasoning_effort(Some("xhigh"))` correctly rejects that unsupported value for B.
3. `set_reasoning_enabled(false)`, then `set_reasoning_enabled_with_commit(true, ...)` succeeds.
4. Live execution snapshot now combines B with unsupported `xhigh`; the commit callback receives exactly that invalid model/effort pair.

```
reasoning toggle: active=model-b, supported=["low"], after_model_switch=low,
  direct_xhigh=rejected, after_off_on=Some("xhigh"), commit=xhigh
```

This is not an invalid input configuration: the baseline A/xhigh and selected B/low are valid. The normal toggle introduces the invalid combination.

### Mechanism and reachability

- `core/runtime/settings.rs:57-86`: model selection honors the selected entry's efforts/default.
- `core/runtime/settings.rs:183-198`: explicit effort selection rejects unsupported effort.
- `core/runtime/settings.rs:138-155`: enabling reasoning restores `configured_reasoning()` when effort was cleared, without any model catalog validation.
- `core/runtime/settings.rs:264-273`: configured defaults belong to the published provider profile (baseline model A), not the current runtime-selected model B.
- `app_server/session_selection.rs:204-211`: public AppServer toggle delegates to that setter and supplies normal selection persistence.
- `app_server/stdio.rs:335-343` and `app_server/http/commands.rs:306-318`: public stdio/HTTP routes call the AppServer toggle.

The storage path checks provider consistency, not supported efforts; therefore the bad pair is eligible for durable storage. That downstream persistence conclusion is source-derived, not claimed as an additional disk/restart reproduction. Restoring saved selections intentionally skips discovery because they are assumed to have been validated earlier.

### Evidence and limits

`reasoning-toggle-isolated.log`: 3/3 reasoning tests passed, including the new unique reproducer and two existing reload/rollback controls.

Fixture: a small in-memory `Model` implementing a valid two-entry `ModelCatalog`; installed via the repository's existing test-only `replace_model_for_test`. Real runtime setters, locks, model-switch validation, snapshot and commit callback are used. There are no paid/external model requests. No claim about which real provider rejects or normalizes the value, or about desktop GUI reachability. HTTP and stdio reachability follows the checked production routes.

Test: `audit_reasoning_reenable_bypasses_active_model_catalog_after_model_switch` in `core/runtime/tests/reasoning_reload.rs`. Patch: `reasoning-toggle-repro.patch`.

Fix direction: choose/revalidate an enabled reasoning default for the active model, using the same authoritative catalog semantics as model selection and explicit effort changes. Do not infer supported efforts from model names. Preserve provider profile summary/budget semantics as appropriate, but do not reintroduce an unsupported baseline effort after it was correctly adjusted during model switching.

### Build isolation note

The first attempted run (`reasoning-toggle.log`) reused a sibling checkout's shared target artifact and ran only the two existing tests. It is **not** evidence for this finding. The successful isolated run explicitly compiled this checkout and ran the new unique test. Its target is `/workspace/shared/profile-recovery-round7-target-clean`; package fingerprints were removed from a copied dependency cache before compilation. No hardlinked or shared writable build products are used there.

Re-run with the same toolchain/fixture exports as REPORT, but:

```sh
export CARGO_TARGET_DIR=/workspace/shared/profile-recovery-round7-target-clean
cargo test -p proteus-core --lib core::runtime::tests::reasoning_reload:: -- --nocapture
```
