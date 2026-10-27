# Current Core foundation qualification

Status: **PREPARED; NOT RUN.** This package makes no runtime, performance or merge-readiness claim.

## Exact graph and source boundary

- Core upstream: `1f533a13f20a93bf164f7c8a169553b0b219bb51`, tree `63d2318ca43a920522ab70623e70ca39608b4df8`.
- Private shipping composition: `608b77f6e1146894dcd756fb1607084d7eba500a`.
- Complete instrumented candidate: `cfb259bf068296548efbc263b85df47a94f7f3e6`.
- Stock Modules: `f5336923bcd01e581e64c4fbe84fa7f13388f5a5`, tree `44bab4e63a3c43f0248f8cd47a753eb66ceb9143`, explicitly selected through supported `PROTEUS_MODULES_SOURCE`.
- Modules' stock Core SDK/dev-dependency remains `1f533a13`. Its two Rust test targets do **not** execute our patched host. Core and Modules retain independent lockfiles.
- Core's unchanged default fixture remains older Modules `7fceaebc3bed8add9b0e3091110f59deca86ba46` / SDK `bee0e409e746e2df9db32748d4f8ea02201bd4af`. That is not the graph qualified here.

The 21 exact patches replay against hash-verified current preimages. All six complete plans are checked before any source replacement; only four are executed. Source variants preserve the user's lazy display/resume path, settled history unloading, writer hibernation and retained lease. Strong ownership/recovery/admission prerequisites are semantically integrated rather than restoring stale whole files; the superseded eager startup-worker hunk is omitted. The existing hibernation test independently probes the external stable lock inode.

Included runtime changes are the four copy reductions, PID-guarded primary writer unlock, bounded-age configuration revalidation, and PID-guarded disposable cache-gate unlock. No raw-parser/compact-context optimization or rejected-admission residency candidate is included.

## One bounded run, three source jobs

1. **Baseline.** On `copy_baseline`, build Core and protocol library test executables and run 19 exact controls: 14 green and five assertion-specific expected reds. Then materialize the independently checked `cache_baseline` using the same isolated Cargo target and run nine exact cache controls: six green and three WouldBlock-specific reds. Source, compiler output, test inventory and executable hashes are bound separately before each transition. No full baseline suite is claimed.
2. **Production.** Run two complete stock Modules targets, `codex_compaction` and `codex_model_resume`, once after locked metadata identifies all five pinned stock SDK packages. Then perform the final fresh reference build through Core's supported builder and hash its actual output. Build the unchanged DCP dependency only because canonical Core full requires it. Run `python3 scripts/test.py full --no-run --message-format=json`, then `python3 scripts/test.py full` exactly once. No duplicate standalone protocol/module_swap runs.
3. **Focused.** Build a fresh current Modules reference fixture, compile the complete instrumented Core and protocol libraries, run all 35 direct controls and the retained four-schedule recovery/deletion test, then both complete library executables at four threads. No repeated full workspace or separate integration build.

A receipt-only aggregate independently reclassifies every bounded raw log and requires all current GitHub source jobs to succeed. Foreign head/run/attempt, missing evidence, infrastructure failures, wrong assertions, zero-test filters, unexpected ignores, source changes or stale executables cannot produce PASS.

## Required boundary evidence

Production canonical compilation binds actual Core and protocol library executables and the `broker_v3`, `module_swap` and `hook_runtime` integration targets. Exact required outcomes must occur inside those executable-bound Cargo sections, not merely somewhere in a combined log. The module-swap target retains its exact 16-case inventory.

The lazy-history witnesses include tail-only decoding, settled nonresidency, retained writer lease, canonical first workflow input, clear-operation ownership, and actual subsequent model/workflow requests. In particular, `interruption_during_after_hook_preserves_already_completed_effect` must pass inside the fresh `hook_runtime` target. Its persisted branch inspects the real follow-up `ModelRequestRecorded`, not a later disk read.

Checkpoint controls inspect callback state before unloading. A settled persisted `history().await` reads a disk snapshot; it is never relabeled as resident/live evidence. Optional rejected-admission cleanup is not fixed or newly required here.

Stock Modules targets require nine and 57 exact Linux case identities. Seven named child entrypoints are not additional end-to-end scenarios. Four intentionally killed inherited crash helpers emit start headers but no successful outcomes or terminal summaries under the explicitly inherited `RUST_TEST_THREADS=4`; no speculative output normalization is used. Unexpected output shape fails closed.

## Bounds and provenance

Standard `ubuntu-22.04` runners only; two concurrent source jobs maximum. Each source controller has a 110-minute deadline and 150-minute job limit; aggregate has ten minutes. Cargo uses two build jobs, no incremental build or debug information, and four test threads. Hosted admission requires 8 GiB free and supervised command execution retains a 2 GiB low-water reserve. These are infrastructure bounds, not a guarantee of runner capacity. Dependency/setup steps have separate timeouts; Runner disk/output sampling does not claim to cover apt/rustup downloads.

Budget: four patched-host Core source-arm compilations, three protocol-library compilations counting canonical full, two fresh reference-fixture preparations, and one pair of stock Modules test-target builds/runs (including their stock SDK compilation). Dependencies may be reused only inside the isolated job. No cache restoration, cleanup, paid runner, retry, test serialization, source ignore or gate bypass.

All source/fixture/SDK snapshots and relevant binaries are checked again after use. Rust 1.95.0, Node 22.18.0 and verified ordinary unprivileged bubblewrap 0.13.1 are installed only on ephemeral hosted runners. Official Actions are commit-pinned. Repository permission is read-only, checkout credentials are not persisted, and product commands receive an allowlisted environment. No upstream writes, secrets, native/UI work, advisory submissions or npm audit. DCP is an unchanged canonical regression dependency only, never a development or optimization target.

Raw phase logs, partial receipts and bounded controller self-test logs are retained on failure. Expected negative controls are named execution results, not broad acceptance of a nonzero exit. Counts from overlapping focused/canonical runs are never added into a unique-test or speed claim.

## Preserved failed predecessors

These old-graph runs remain failures and are not retroactively qualified:
- [40476346049](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40476346049): writer-ownership regression failed; historical holder unknown.
- [40480504769](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40480504769): source phases passed, aggregate rejected a tuple/list JSON mismatch.
- [40483121449](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40483121449): metadata-watch fixture failed; historical timestamps were not recorded.
- [40491865543](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40491865543): parallel catalog-cache save assertion failed; exact failing branch and cause unknown.

The first current-graph run [40512677031](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40512677031) also remains **failed / not qualified**. Baseline completed; production stopped before its product compilation/tests because the controller decoded Cargo's combined diagnostic/metadata log as a single JSON document. The controller-only correction retains the complete raw log, accepts exactly one complete strict metadata record, rejects ambiguous or malformed metadata, and uses identical parsing in phase and aggregate. No source patch, test selection, fixture pin or resource bound changed. A fresh exact-head run is required.

## Remaining limits

This package does not establish numerical allocation/latency/RSS benefit or qualify a benchmark. The three-second semantic configuration scan age remains provisional and unmeasured; it is not a scheduler guarantee. Existing metadata fixture prerequisites are explicitly amended, not called unchanged. Unlock failures retain best-effort close fallback, not an OS-failure guarantee. Core source tests, selected stock Modules targets and the explicit fixture graph must all pass fresh before any qualification claim.
