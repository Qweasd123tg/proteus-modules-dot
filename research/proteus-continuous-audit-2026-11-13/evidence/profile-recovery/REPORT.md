# Proteus: profile publication and recovery, continued audit

2026-11-13. Isolated local tests only. No production patch, commit, push or PR.

Versions:
- Core main verified with `git ls-remote`: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Official reference-module fixture source: Modules `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Test checkout: `/workspace/shared/profile-recovery-round7`.

## 1. P2: fast external revert after UI Save can permanently desynchronize the live profile

**Confirmed, high confidence.** The watcher keeps a private `applied` fingerprint. UI Save publishes a new profile immediately but does not update that fingerprint. Until polling observes the new file, the old fingerprint remains. If an editor Undo, checkout or other local operation returns the file to the prior content, the `expected == applied` fast path considers it unchanged before comparing against the actually published configuration.

Actual chain using real AppServer `set_profile_config`, real profile reader/writer and official process fixture:

1. Launch profile A with permission mode Normal.
2. Let the watcher settle on A.
3. UI Save B with mode Auto succeeds, persists B and publishes B.
4. Before watcher observes B, restore file A.
5. Four later forced semantic scans all skip refresh, with no error.

Observed:

```
fast revert: disk=Normal; published=Auto; live=Auto; reload_error=None
```

Control: let the watcher observe B after Save, then restore A. The same reader/publication correctly reloads Normal:

```
observed save control: disk=Normal; published=Normal; live=Normal
```

Sources:
- `crates/proteus-core/src/app_server/profile_watch.rs:59-61`: initial watcher fingerprint.
- `profile_watch.rs:126-142`: outdated `applied` short-circuit precedes comparison with actual current configuration.
- `app_server/profile.rs:49-62`: publication updates runtime/config, not watcher-owned fingerprint.
- `app_server/config_builder.rs:227-237`: UI Save uses shared publication.

Tests:
- `audit_fast_external_revert_after_ui_save_leaves_live_profile_stale`
- `audit_external_revert_after_watcher_observed_ui_save_is_applied_control`

Both PASS while asserting the current defect/control. `watcher-revert.log` records 2/2. The test harness uses the repository's existing controlled `Polling` seam, not a reimplemented watcher. The originally launched wall-clock watcher is stopped and the same live server state gets a controlled watcher. Production save/load/prepare/publication remain unchanged. This isolates scheduling deterministically; no timing probability or desktop GUI behavior is claimed.

Impact: profile file and current session disagree indefinitely, including permission mode. A fresh session uses the file while the saving session keeps old effective settings. Ordinary periodic rescans do not repair it; another effective profile change/restart is needed. This is separate from earlier findings about failed-fingerprint retry or erased startup overlays.

Fix direction: ensure skip decisions compare against the published profile, or update the watcher's publication baseline through a versioned/shared publication state. Preserve independent session permission overrides: blindly resetting runtime on every scan would be an incorrect fix. Add the fast-revert regression plus control before changing synchronization.

## Scope and non-findings

- Runtime model-selection persistence takes the configuration from the assembly under `reload_lock`; the suspected stale `AppServer.config` selection-binding race was not present.
- History excluding process component descriptors is documented as partial managed-field history; not asserted as a defect.
- Model-route changes invalidating persisted selections but retaining a live override are a possible semantics inconsistency, not yet a reported defect.
- No claim of full line-by-line coverage of every repository.

## 2. P2: Save after a missing profile creates an unreadable profile when instructions use files

**Confirmed for TOML, high confidence.** This is a recovery-path defect, not ordinary Save of an existing source.

`AppConfig::load` resolves each instruction file by adding its contents to `entry.text`, but retains `entry.file`. That in-memory representation is valid for assembly. It is not valid as source: the same loader rejects entries containing both keys. If the profile disappears while the app remains running, Config Builder intentionally falls back to live `self.config`, and the missing-file persistence branch serializes it in full. The prepared runtime is valid, so Save acknowledges success without checking whether the generated source can be read back.

Reproduction with real AppServer + official reference module:

1. Write `profile.toml` with `[[instructions]] file='rules.md'` and a valid process model.
2. Load and launch it. Run an ordinary Save while the source exists: success, saved instruction has only `file`, reload succeeds (control).
3. Remove the temporary fixture's source file, leaving the loaded app and `rules.md` intact. Equivalent state could result from a mistaken local move/delete.
4. Save `permission_mode=Plan` in the app. It recreates the file and returns a successful `permission_mode='plan'` snapshot.
5. Reading the recreated profile fails, and the next UI Save also fails.

Observed:

```
missing-profile save ACK=plan
reload error=instructions entry must set either text or file, not both: rules.md
saved instruction={ file = "rules.md", kind = "System", priority = 100,
                    text = "Keep the fixture answer short." }
```

Sources:
- `core/config/loading.rs:124-144`: reject file+text source, then resolve file by retaining both in memory.
- `app_server/config_builder.rs:157-161`: missing source falls back to the resolved live configuration.
- `app_server/config_builder/persistence.rs:88-96`: missing file gets full serialized config.
- `app_server/config_builder.rs:227-237`: commits the generated source and publishes success.

Test: `audit_save_after_missing_profile_serializes_resolved_instruction_twice`.

Impact: the live session remains usable, but restart/resume from that profile and subsequent configuration edits fail until the person manually repairs the file. No lost instructions or broken session journal is claimed. JSON and missing directory profiles were not reproduced; only the TOML source-file branch is asserted.

Fix direction: separate unresolved source configuration from resolved runtime configuration, or explicitly project file-backed instructions to a valid source representation before initializing a missing profile. Preserve the file reference instead of silently freezing its current contents. Validate generated source round-trip before reporting successful persistence.

## Final verification

`adjacent-suite.log`:
- Config Builder adjacent suite: 7 passed, including the recovery reproducer and existing source/symlink/directory/JSON/concurrency tests.
- Profile watcher adjacent suite: 5 passed, including both new deterministic scheduling probes and existing file/UI propagation/instruction refresh/lifetime tests.
- Total: 12 passed. These are repro/control tests asserting the observed defect, not a claim that defects were fixed.

`git diff --check` passed. Only two test files changed, no production source. `core-repros.patch` contains the complete test-only diff. No external provider calls, paid API calls, publication or PR creation.

Re-run:

```sh
source /workspace/shared/proteus-toolchain/env.sh
export CARGO_TARGET_DIR=/workspace/shared/proteus-runtime-audit-target
export PROTEUS_TEST_REFERENCE_MODULE=/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module
cd /workspace/shared/profile-recovery-round7
cargo test -p proteus-core --lib app_server::config_builder::tests:: -- --nocapture
cargo test -p proteus-core --lib app_server::profile_watch::tests:: -- --nocapture
```

### Independent target recheck

After detecting shared Cargo target reuse on an unrelated third probe, both suites above were rerun in a private target. `isolated-adjacent-suite.log` confirms all 12 tests, including every unique reproducer/control, with the same output. `ADDENDUM-reasoning-toggle.md` adds a third confirmed host-side defect and 3 further passing tests. Total across the private-target suites: **15 passed**, no production edits. The original two-finding patch remains unchanged; the third has its own `reasoning-toggle-repro.patch`.
