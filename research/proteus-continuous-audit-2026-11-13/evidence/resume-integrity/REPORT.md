# Proteus: round 9, cold resume and user-data integrity

Date: 2026-11-13. Independent audit; no production edits, commits, pushes or PRs.

## Versions and reproduction scope

- Proteus-core `89997df995df7c39b713e16aba216ecb19c8f497`.
- Proteus-modules `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Both versions rechecked against their origin `refs/heads/main` during this pass.
- Isolated Core checkout: `/workspace/shared/resume-integrity-round9`.
- Rust 1.95.0. Real reference-module process from that Modules checkout and existing Python process-model/AfterTool fixtures. No live provider, API key, user workspace, or Desktop GUI.
- `tests.patch` adds only three focused diagnostic tests to existing integration targets. These tests assert the observed defects, not a repaired contract. Production files unchanged.

## 1. P2: rejected image permanently blocks later text-only turns, including cold resume

### Reproduced

1. Use a model descriptor with `supports_image_input=false`.
2. A normal text request succeeds (`Images received: 0`).
3. Submit a valid PNG; shaping rejects it with `model 'fixture' does not support image input`.
4. Submit plain text with no attachment. The same error returns without a provider call.
5. Drop runtime, cold-resume the session, submit another plain-text message. Same error.
6. Canonical settlements are `[Success, Error, Error, Error]`; only the baseline request reached the model process.
7. `clear_history()` permits plain text again. This is a demonstrated workaround but removes working conversation context.

The rejected PNG remains in canonical model history. The check scans all history, not just this turn. Failure does not roll back or otherwise make that image non-executable. This is different from the previously reported model-adapter image-content loss.

### Sources

- [User message persists before workflow execution](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/turn.rs#L287-L306).
- [RequestShaper rejects any image anywhere in model history](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/model_standard/shaper.rs#L17-L27).
- [Current existing test checks initial rejection and image retention, but not follow-ups](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/tests/execution_boundary/images.rs#L138-L165).

Test: `images::audit_round9_rejected_image_poisoning_persists_after_cold_resume`.
Evidence: `images-controls.log`.

Fix direction: distinguish retained audit/transcript input from valid executable context, or fail an incompatible input before committing it to executable history. A generic Core policy must account for workflows that intentionally process images without sending them to a vision model; simply rejecting every image for every text-model workflow would be too broad.

## 2. P2: supported stopped-session relocation preserves image preview but breaks continuation

### Reproduced

1. Run an image-capable process-model turn with a valid PNG; it succeeds.
2. Drop the runtime and move its whole session directory under another existing workspace's canonical encoded parent.
3. Cold-resume. Authoritative workspace correctly changes to the target.
4. The image bytes are physically present in the new session directory; `image_bytes(id)` still returns the exact PNG.
5. Restored canonical `ImageRef.path` still names the old session directory.
6. A normal text follow-up reaches the model path-reader with that obsolete path and fails with ENOENT, despite the intact attachment in the new location.

This is not an unsupported move of a live writer: the runtime is dropped first. Moving a stopped session to a different encoded workspace is expressly documented.

### Sources

- [Documented relocation semantics](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/runtime-and-events.md#L1629-L1638).
- [Admission stores a canonical absolute path in ImageRef](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/images.rs#L70-L86).
- [New runtime ImageStore follows current session directory](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/builder.rs#L276-L287).
- [Production model adapter consumes ImageRef.path](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/images.rs#L4-L18).

Test: `images::audit_round9_supported_session_relocation_breaks_image_context`.
Evidence: `images-controls.log`.

Fix direction: durable attachment identity should be session-relative or rebound to the current attachment store at the execution boundary. Do not casually rewrite canonical message parts under their existing IDs; Core's part-identity validation makes that a separate compatibility concern.

## 3. P2: crash between durable ToolEffect and AfterTool completion creates false `aborted` model context

### Reproduced through public app-server resume

1. Real `coding.codex_loop` calls `apply_patch` and creates `smoke.txt`.
2. Core persists `ToolEffectRecorded { ok: true, output: "added smoke.txt" }`.
3. Existing `process_hook.py` fixture blocks inside AfterTool. At this barrier copy the complete canonical session into an isolated snapshot, before `ToolResultRecorded` or `TurnSettled` exists. This is a crash-equivalent prefix; the active source is never truncated or modified.
4. Cancel the original gracefully and verify that its normal settled history preserves the successful result. This is the positive control.
5. Resume the copied prefix through `AgentAppServer::launch_resumed`.
6. Cold transcript reports the tool as `status=done, result="added smoke.txt"`.
7. Submit `continue without tools`. Inspect the resulting durable model request: the same call ID is represented by `ToolResult { ok: false, output: "", error: "aborted" }`.
8. The actual file still exists; the raw effect still exists in journal. No duplicate side effect was executed by this test.

Cause: ToolEffect records update lifecycle metadata, but only final ToolResult or TurnSettled folds the effect into canonical working history. Writer recovery returns history without folding an abandoned turn's known effect. The Codex workflow consequently mistakes a known completed effect for a missing result and synthesizes its request-only `aborted` result. Display recovery separately recognizes raw effects, so user and model see contradictory outcomes.

### Sources

- [ToolEffect retained only in lifecycle state](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/projection.rs#L372-L390).
- [TurnSettled folds pending effects](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/projection.rs#L437-L462).
- [Writer resume returns the unaugmented validation history](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/storage/initialize.rs#L18-L35).
- [Cold transcript accepts raw ToolEffect when no final result exists](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/transcript/journal.rs#L196-L204).
- [Codex workflow synthesizes aborted result for a missing output](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/codex_recovery.rs#L44-L72).

Test: `audit_round9_crash_prefix_discards_durable_effect_from_next_model_context`.
Evidence: `effect-prefix-app-server.log`.

Fix direction: on execution recovery, reconcile known committed effects from abandoned turns before exposing the next workflow history, distinguishing absent final hooks from absent actual effects. Never fabricate tool success when no effect was durably recorded. Potential repeated work is a consequence to assess, not a reproduced claim here.

## Commands and results

```bash
source /workspace/shared/proteus-toolchain/env.sh
export PROTEUS_TEST_REFERENCE_MODULE=/workspace/shared/proteus-review-20261112/core/target/sources/modules/target/debug/proteus-reference-module
export CARGO_TARGET_DIR=/workspace/shared/proteus-runtime-audit-target
cargo test -p proteus-core --test execution_boundary images:: -- --nocapture
# 5 passed: two new diagnostics plus all three original image controls.
cargo test -p proteus-core --test hook_runtime audit_round9_ -- --nocapture
# 1 passed: real process effect, graceful-cancel control, cold app-server transcript and next model request.
git diff --check
# passed
```

The shared Cargo cache was reused; logs show recompilation from this isolated checkout and the unique new test names, ruling out an accidental run of a stale test binary. No complete Rust gate or GUI/live provider run was performed. No production patch is claimed. The crash boundary was reconstructed with a complete validated on-disk prefix, not actual power-loss or SIGKILL testing.
