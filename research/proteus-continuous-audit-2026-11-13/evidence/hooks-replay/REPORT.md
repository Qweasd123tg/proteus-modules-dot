# Hook scheduling and hook replay audit

## Scope / reproducibility

- Core remote `main` rechecked against `git ls-remote`: `89997df995df7c39b713e16aba216ecb19c8f497` (2026-11-13).
- Isolated clone: `/workspace/shared/scheduling-hooks-audit`.
- Original Core checkout remains untouched. Only two test files were modified in the isolated clone. No production patch, commit, push, PR, user data, real provider request or external effect.
- Modules hook and workflow implementations were reviewed read-only at `3270dc0f894eaf4d0360306052b806099b8f5351`. This is not a cross-version process integration run.
- `reproduction.patch` contains both diagnostic probes. `git diff --check` succeeds. Probes assert observed defects, not desired post-fix invariants.

## H1. Hook callbacks do not honor serial tool scheduling (confirmed behavior, qualified hardening finding)

A `BeforeStop` hook that concurrently invokes two copies of a registered tool with `supports_parallel_tool_calls = false` runs both bodies concurrently. The equivalent sibling calls from a ToolHost have a shared/exclusive gate.

### Source chain

1. [`execution_hooks.rs:82-96`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/execution_hooks.rs#L82-L96) creates one invocation-bound facade for each hook, allowing tools in BeforeStop, BeforeModel, BeforeContext and BeforeToolSelection.
2. [`extension_operations.rs:57-84`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/extension_operations.rs#L57-L84) routes each HookHost tool callback directly to BoundTools; there is no sibling gate or registered parallel-permission check here.
3. In contrast, [`extension_operations.rs:139-182`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/extension_operations.rs#L139-L182) fences ToolHost siblings and gives descendants a separate gate to avoid a reentrant deadlock.
4. Process hooks call the same facade through [`operation_host.rs:35-47`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/operation_host.rs#L35-L47). `HookModuleHost` is Send + Sync and its execute callback takes `&self`, so concurrent callbacks are supported by the interface. The process boundary was source-traced, not executed in this probe.

### Evidence / consequence

`audit_hook_siblings_ignore_serial_tool_permission` uses the real RuntimeHookChain, real BoundTools, real HookHost facade, normal registry and policy path, and a synthetic read-only serial tool. Both bodies enter before either is released: **maximum overlap = 2**. Requested facts retain Hook owners. Four existing nested scheduling controls pass, including exclusive serial fences, parallel overlap, nested serial grandchildren and cancellation of queued siblings.

Potential effect: a custom hook author using concurrent callbacks can unknowingly overlap tools that are only safe serially. This is not a bypass of policy, approval, or the hook phase restrictions. The probe does not claim an actual lost edit.

**Important qualification:** the `ToolSpec` field's narrow code comment says exclusivity is required “within a workflow tool-call sequence”; documentation of the existing child gate is in the Tool/code-mode section. No concurrent tool callbacks were found in shipped hook implementations during this pass. Therefore this is a verified inconsistency/gap to settle in the extension contract, not evidence that an existing default profile races today. Keep separate from confirmed user-facing defects unless the intended guarantee includes all extension-owned tool siblings.

Fix direction if that guarantee is intended: give each hook invocation a cancellation-aware shared/exclusive sibling gate using the registered tool spec, reusing the ToolHost gate abstraction; keep a fresh gate for descendants rather than a global gate. Otherwise explicitly document the different HookHost contract and require the hook to serialize calls itself.

## H2. Replay rewrites literal hook output as if it were a call identity

**Confirmed narrow replay correctness defect.** A valid ToolOutput string that happens to equal a recorded call ID is changed during ID remapping. The replay's own final equality check then rejects a valid recorded result.

### Source chain

1. [`hooks.rs:143-151`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_replay/replay_runtime/hooks.rs#L143-L151) rewrites the saved HookResponse before applying it.
2. [`hooks.rs:415-441`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_replay/replay_runtime/hooks.rs#L415-L441) serializes the whole response, recursively replaces **every string** equal to a map key, then deserializes. It does not distinguish typed identity references from opaque output text, instructions, enum strings, or tool names.
3. [`hooks.rs:180-188`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/workflow_replay/replay_runtime/hooks.rs#L180-L188) checks the replayed event against its recorded output. Normal result normalization changes call IDs/metadata, not literal output; the altered output therefore fails.

### Evidence / consequence

`audit_replay_rewrites_literal_hook_output_equal_to_call_id` runs real ReplayState and ReplayHooks using a valid trace and result. A call is remapped from `recorded-call` to `actual-call`; the hook's literal output is `recorded-call`.

Observed internal response: `ToolOutput { output: "actual-call" }`.

Observed failure: `hook boundary after_tool replayed output differs from recorded output`.

The original invariant test expected this valid trace to replay successfully and failed (`replay-invariant-failure.log`). The diagnostic now asserts the observed error. Eight existing hook replay controls also pass, including the same remapping path with unrelated output `shaped` and successful raw-then-transformed result replay.

**Boundary:** this is a false divergence during replay when actual call IDs differ and an opaque string matches an old call ID. It is not demonstrated live conversation or journal corruption; the final equality check rejects the altered output. Common provider-recorded calls retain their IDs on replay, so those calls do not trigger this case. Workflow-generated fresh identities are why the supported replay remapping path exists; no current default profile's natural occurrence frequency was measured.

Fix direction: match typed HookResponse variants and rewrite only actual identity-bearing fields. Preserve ToolOutput.output, instruction text and other literal data exactly. The same generic helper is used on checkpoint ACK messages (`checkpoints.rs:268-270`); that path deserves a separate regression test before claiming it is fixed too.

## Reviewed boundaries / non-findings

Read line-by-line in this focused pass: RuntimeHookChain, runtime turn lifecycle notifications, reviewed workflow continuation loop, bound tool hook/invocation paths, invocation-bound extension facades, operation dispatcher, hook process adapter, HookHost/ToolHost contracts, hook replay transformation and normalization, nested scheduling tests; Modules hook-pack and claude-command-hooks entry; codex streamed tool scheduling and ticket gate. This is not a claim of whole-repository coverage.

- TurnSettled uses the admission snapshot, not whatever config is current later. No snapshot replacement bug found there.
- Auxiliary hook model operations deliberately skip recursive BeforeModel hooks; the existing tests cover that path.
- Before/AfterTool nested tools remain explicitly unavailable. The scheduling finding does not change those restrictions.
- Process broker rejects invocation completion with outstanding callbacks; no unowned callback leak finding is reported.
- Previously reported late-turn cancellation inconsistency and other known races are not repeated as new findings.

## Commands

```bash
source /workspace/shared/proteus-toolchain/env.sh
cd /workspace/shared/scheduling-hooks-audit
export CARGO_TARGET_DIR=/workspace/shared/proteus-runtime-audit-target
cargo test -p proteus-core --lib core::extension_operations::tests --offline -- --nocapture --test-threads=1
cargo test -p proteus-core --lib core::workflow_replay::replay_runtime::hooks::tests --offline -- --nocapture --test-threads=1
```

## Final verification

After formatting the two test-only additions:

- `extension-operations-tests.log`: **9 passed**, including the scheduling probe and all existing extension operation controls.
- `replay-tests-final.log`: **9 passed**, including the replay probe and all existing hook replay controls.
- `git diff --check`: passed.
- `git apply --check reproduction.patch` against unchanged original Core: passed.
- Original Core `git status --short`: clean.
- No production file changed. Total patch is 161 added test lines across 2 files.
