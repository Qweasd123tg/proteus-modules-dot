# COS-1: non-object directory fragment panics before reload error handling

Status: independently source-reviewed candidate. Suggested priority: **P3**, malformed-configuration robustness and background reload liveness, not a valid-configuration failure or a security claim. No Proteus/Rust code, test, fixture, provider or UI was run. No production change.

## Baseline and contract

Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. Source hashes were checked; raw artifacts are not included. Rust tools are unavailable. Paths and line numbers below refer to that baseline.

`docs/guides/configuration.md:24–27` supports directory profiles, lexicographic `.toml`/`.json` fragments and a final `config-builder.toml` overlay. Lines 1477–1491 describe automatic rereading, retained last-good assembly on error, and `ProfileReloadStatus` error/recovery reporting. The finding is about graceful handling of a syntactically valid but invalid-shape JSON document, not a promise that scalar configuration is valid.

## Minimal source-derived witness

A profile directory selected through an explicit absolute path contains exactly two regular files:

* `a.json`: `null`
* `config-builder.toml`: an empty, valid TOML document

Calling `AppConfig::load(Some(directory_path))` reaches the panic below before final `AppConfig` deserialization can return an invalid-configuration error. This is an unexecuted reproduction recipe, not an observed Rust result.

1. `core/config/loading.rs:351–362` parses JSON into arbitrary `serde_json::Value`.
2. `load_config_file_value:219–223` returns the value unchanged because `take_config_includes:237–239` returns no includes for a non-object.
3. `load_config_dir_value:194–199` initializes an object, then folds ordinary files through `merge_config_value`. Its non-object arm at 374–375 replaces the whole accumulator, so `null` leaves `merged = Value::Null`.
4. The valid builder overlay is loaded at 201. At **204**, `merged.as_object_mut().expect("config merge is an object")` panics while trying to remove the three builder-managed keys.
5. `load_path:72–78` would normally deserialize the merged value into `AppConfig` and contextualize a `Result::Err`, but never reaches that boundary.

Exact precondition: a non-object must remain the final result of the ordinary-fragment fold. A later ordinary object fragment can replace it and avoid this panic. This is not a claim that any non-object anywhere in any include graph panics.

## Integration consequence: the watcher bypasses its recovery loop

`app_server/profile_watch.rs::start_with_polling:66–161` launches the polling loop with `tokio::spawn` and does not retain its `JoinHandle`. At 98 it directly awaits `AppConfig::load_observed`; only returned errors become `Input::Invalid` at 107. The two-equal-input debounce and error publication occur later, at 111–122. A load panic therefore precedes both safeguards and never follows this input's normal error/recovery path.

Under ordinary Tokio panic-unwinding behavior, the panic ends this spawned watcher task. Its later polls cannot observe a repaired profile. This conclusion is a source inference, not a measured task exit: the lockfile pins Tokio 1.52.2 (`Cargo.lock:2094–2097`), whose [JoinHandle documentation](https://github.com/tokio-rs/tokio/blob/tokio-1.52.2/tokio/src/runtime/task/join.rs) describes panic capture into a join error and detachment when the handle is dropped. There is no local catch/restart in the inspected watcher. Do not generalize this to an unconditional whole-process crash or all possible panic/runtime policies.

For a live-watch regression scenario, begin with a fully valid directory profile plus overlay and a running watcher, then write `null` to the last-sorted ordinary JSON fragment and allow a semantic scan. Repair that file with a valid, semantically changed configuration. The current code path cannot poll that repair after this task exits. The previously published assembly remains unchanged because this scan never publishes a replacement. A separate manual Save or creating a new watcher is outside this failed task; this is not a claim that restarting the whole application is the only possible recovery.

## Controls and evidence limits

* Malformed JSON syntax returns a parse error before merging; it is not this panic.
* Without a builder overlay, this `expect` is not reached; a final non-object instead reaches normal deserialization rejection.
* Direct single-file loading has no directory-overlay path.
* A later ordinary object fragment replaces `null` and prevents this exact panic.
* A malformed overlay returns its parsing error before the `expect`.
* An object accumulator with a valid overlay reaches schema validation normally.
* Arrays and scalar JSON can satisfy the same non-object precondition; the minimal witness needs only `null`.

The separate abstract model (not included here) is our own finite Python model of the source fold and boundary ordering. Its output checks these branch distinctions. It does not import or execute Proteus, emulate full AppConfig validation, or establish Tokio scheduling, filesystem timing or live watcher behavior. Existing configuration and watcher test sources were inspected as controls; no claim of exhaustive test inventory is made.

## Small correction and system simplification

At minimum, replace the unconditional object `expect` with a contextual `Result` error for a non-object directory accumulator. This preserves the current recursive merge semantics and lets the existing invalid-input/recovery machinery do its job. Do not silently coerce `null` to `{}` and hide invalid input. A stricter design could validate each configuration document's root as an object before its merge, but that changes currently accepted fragment-fold behavior and should be an explicit contract decision, not an incidental fix. Nested arrays/scalars remain valid values.

The useful simplification is to make the root-shape invariant explicit at the configuration-reader boundary, instead of maintaining a parallel panic path alongside `Input::Invalid`. A broad panic supervisor alone would not fix the loader's Result contract and is not necessary to address this witness.

Unexecuted regression plan: (1) directory null plus overlay returns contextual `Err` without unwinding, with array/scalar and all controls above; (2) deterministic watcher polling on valid → invalid-shape → valid-but-changed profile reports failure then recovery/publication and retains polling liveness. Prefer existing controlled polling over wall-clock sleeps, and repair to a changed semantic fingerprint rather than an identical one.

## Dedup and review

Targeted published-report review found adjacent but different causes: `config-validation/REPORT.md` concerns unknown module-config slots accepted by Save and later rejected by the reader; `profile-recovery/REPORT.md` covers stale applied fingerprint after rapid reversion and instruction file/text serialization; `state-install/REPORT.md` covers overlay/include managed-state behavior. Targeted searches of the available prior DOCX text did not identify this root-shape `expect` chain. This is not an exhaustive novelty claim; PR91–99 were also checked: their cache/lifetime/timeout/identity/ACP/default-helper findings do not contain this root-shape panic.

Independent reviewer confirmed the loader chain, exact last-result precondition, normal-error controls and watcher scope. Independent review caveats are incorporated. Earlier instruction-base and diagnostic-symlink leads from this pass were not promoted: stock instruction fragments deliberately use the top-level profile base, and directory diagnostic enumeration has no established authoritative-input contract.

## Pinned source anchors

Key source files were not changed by delivery PR87–89.

- [core/config/loading.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L194-L208)
- [core/config/loading.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L351-L375)
- [app_server/profile_watch.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile_watch.rs#L66-L122)
