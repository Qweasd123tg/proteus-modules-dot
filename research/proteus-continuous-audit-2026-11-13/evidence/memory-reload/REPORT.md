# JSONL memory: failed partial append poisons later successful memories across reload

## Status and source pin

Confirmed in two end-to-end runs using the real shipped memory module. Proposed P2 durability/recovery defect, conditional on a partial write failure. This is **not** the known shell generation collision or lost subagent resume, and **ReloadTools does not cause the initial corruption**.

- Core clean HEAD/main: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Modules clean HEAD/main: `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Modules uses its unchanged Cargo.lock, Core dependency `b5fac84245b075896c24763b3aebac79b4375c2e`.
- Core binary SHA256: `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`.
- Memory binary SHA256: `85ca5e582712e1f8ece3e6358e96c7a1f71325f571814d598ca9d46af83e9730`.
- Source trees unchanged; nothing published.

## Real execution path

`proteus server stdio` → model-free workflow/v20 fixture → normal `host.tools.execute_batch` and explicit local fixture policy → real `proteus-memory-pack-module` → local disposable JSONL file.

The wrapper lowers `RLIMIT_FSIZE` **only for its own memory worker process** to 512 bytes. It ignores SIGXFSZ so the OS returns EFBIG rather than terminating the process. No global settings, real user files, credentials, models or network services are touched. The limit is lifted for the next worker by changing a fixture limit file, not by modifying the runtime profile.

1. `remember_fact("known-good durable fact")` succeeds; default recall succeeds.
2. `remember_fact("X" repeated 1024)` returns `ok=false`, `File too large (os error 27)`.
3. The JSONL file is exactly 512 bytes: intact first record/newline plus a partial second record without a newline.
4. Default `recall_memory` now fails on line 2: `EOF while parsing a string`.
5. Lift the fault, call `ReloadTools` with unchanged profile: epoch 0 → 1, reload succeeds.
6. Recall from the new worker still fails on the partial persisted tail.
7. New `remember_fact("successful-after-reload")` now returns **ok=true / Remembered**.
8. Recall specifically for `successful-after-reload` fails on line 2 (`expected ',' or '}'`): the successful append was concatenated directly onto the prior broken JSON fragment.
9. Positive prefix control `recall_memory(query="", limit=1)` still returns the original known-good record. It has not been overwritten; queries that reach the damaged line fail before returning accumulated results.

Healthy control with a 1 MiB limit: both the small and same 1024-character memory succeed, reload succeeds, recall after reload returns both. The fixture and reload alone do not generate the failure.

## Root cause

- `context_provider/memory-pack/src/lib.rs:96-115`: append opens the shared file, serializes a record/newline, then `write_all(&line)?`. A short write followed by error leaves the written prefix in place. There is no transactional record boundary, rollback or tail recovery.
- `lib.rs:118-146`: recall parses every visited line and returns an error on malformed JSON, including an incomplete last line. This is intentional behavior for genuinely corrupt committed lines, but there is no distinction between those and an interrupted append.
- `lib.rs:106-115`: later writes blindly append to the same file without checking whether the last record was completed.
- `tools.rs:70-76`: after that later append succeeds, the tool unconditionally reports `Remembered`, despite creating a record that cannot be read back normally.
- `lib.rs:154` and Core `app_server/profile.rs:91-94`: reload creates fresh store/worker state but reopens the same on-disk memory; rebuilding the registry cannot repair the durable tail.

Source links:

- https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context_provider/memory-pack/src/lib.rs#L96-L146
- https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context_provider/memory-pack/src/tools.rs#L70-L86
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile.rs#L81-L95

## Scope and caveats

Proved EFBIG/partial-write behavior with isolated fault injection, twice, and survival across ReloadTools. Real disk exhaustion/ENOSPC, power loss, machine crash and full root restart were not induced. They should not be stated as observed. Core startup and reload themselves remained successful; the demonstrated failure is memory tool storage/recall.

The automatic memory context provider calls the same `store.recall` (`provider.rs:24-25`), so it shares the parsing failure by code. This repro did not separately run a repo-aware context build.

No evidence of concurrent-writer corruption was obtained in this pass. The per-instance mutex is important for a fix: old and new generations or independent sessions may coexist, so a naïve rollback using `set_len(old_size)` without interprocess serialization can truncate someone else's committed append.

## Fix direction / regression contract

Use a durable record transaction or interprocess-serialized append with unambiguous completion boundaries and safe interrupted-tail recovery. A new successful remember must be retrievable after a previous failed append and reopen/reload. Preserve earlier complete records; do not silently skip arbitrary malformed interior records. If recovery is not possible, reject subsequent writes instead of claiming to have stored usable memory.

Regression should cover: existing valid record → partial failed append → storage restored → reopen/reload → successful append → both previously acknowledged and newly acknowledged records retrievable; also concurrent independent store instances.

## Artifacts and replay

- `repro_memory_partial_append.py`, `limited_worker.py`, `workflow.py`.
- `run-1.log` and `memory-run-1794563716261201190/`.
- `run-2.log` and `memory-run-1794563749028741663/`.
- `control.log` and `memory-run-1794563772103801372/`.
- Each run contains raw wire/journal, stderr, unchanged profile, result.json, actual memory file. Fault runs also preserve `after-failed-write.bin` before the successful append.
- Build log: `/workspace/shared/trace-component-reload-memory-build.log`.
- Build: `source /workspace/shared/proteus-toolchain/env.sh; CARGO_TARGET_DIR=/workspace/shared/trace-integration-round8-module-target CARGO_PROFILE_DEV_DEBUG=0 cargo build --locked --offline -p proteus-memory-pack-module` in clean Modules checkout.
- Repro: `python3 /workspace/shared/trace-component-reload-memory-evidence/repro_memory_partial_append.py`.
- Control: same command with `--control`.

## Other state checked without a new confirmed defect

Plan/skills/context/policy/default hooks mostly stateless; model-pack retains quota/catalog caches, not required durable memory. Rust-LSP holds a recreated workspace client/overlays, whose reload reset is expected; previously known stale-overlay issue was not counted again. Shell capture store already has a generation in its handles and explicitly ephemeral file ownership, so resetting it was not counted as a new collision. SQLite memory reopens a durable database; no reload-specific corruption demonstrated.
