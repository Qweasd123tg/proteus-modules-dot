# BeforeModel consumes a model deadline that cannot interrupt it

## Result

Confirmed narrow P2 at the Core hook/model boundary. A valid, cancellation-cooperative `BeforeModel` hook is allowed to run beyond `runtime.model_timeout_ms`, without receiving model-timeout cancellation. When the hook finally returns, the already-expired model deadline rejects the still-unsent provider request. The same amount of work in `BeforeContext` does not consume that model deadline.

This is **not** the previous BeforeModel instruction-estimation defect, an output-budget issue, or provider-token loss. It concerns the lifetime of the model call and its nested hook operations. The reproduction uses a custom hook through the supported process `hook/v6` contract; no claim is made that current shipped instruction-only hooks normally run this slowly.

Core: `89997df995df7c39b713e16aba216ecb19c8f497`.
Modules: `3270dc0f894eaf4d0360306052b806099b8f5351` (the module workspace's Core dependency remains pinned to `b5fac84245b075896c24763b3aebac79b4375c2e`). Remote main matched these local revisions during this pass.

## Real process reproduction

`run.py` launches the existing Core executable, production `coding.codex_loop`, `codex_context`, native OpenAI Responses adapter, and a Python test-only hook. The hook uses the repository's own `component_runtime.py` helper and checks cancellation throughout its artificial delay. All provider traffic terminates at a loopback HTTP/SSE fixture with valid successful outputs. There are no real credentials or external model calls.

The standard model deadline is 400 ms, workflow timeout 6000 ms. The model export's explicit timeout is 6000 ms, separating transport timeout from the Core model deadline. Disabling the Core model timeout therefore does not leave the external process unbounded.

| Case | Relevant work | HTTP requests | Result |
|---|---|---:|---|
| No hooks | Immediate provider | 1 | Success |
| No-op hook | Immediate provider | 1 | Success |
| Slow BeforeModel | 1200 ms cooperative hook | **0** | Model timeout, after ~1.39 s turn elapsed |
| Same delay in BeforeContext | 1200 ms cooperative hook | 1 | Success |
| Slow BeforeModel, model timeout disabled | 1200 ms hook | 1 | Success |
| Slow BeforeModel, workflow timeout 900 ms | 3000 ms hook | 0 | Workflow timeout; **hook receives cancellation** |
| Fast provider | 260 ms HTTP | 1 | Success |
| Slow provider | 1200 ms HTTP | 1 | Model timeout promptly, ~0.54 s total turn elapsed |
| One auxiliary call inside BeforeModel | Each HTTP 120 ms | 2 | Auxiliary and main calls succeed |
| Two auxiliary calls inside BeforeModel | Each HTTP 260 ms | **2, both auxiliary** | Both helpers succeed; main is rejected before HTTP |
| Same two helpers, model timeout disabled | Each HTTP 260 ms | 3 | Both helpers and main succeed |

Total: **11 process sessions and 13 captured HTTP requests**. Turn elapsed includes setup/context work and is not presented as the exact model-call duration. `analysis.json` and hook monotonic timestamps provide the exact hook duration and cancellation evidence.

### Particularly non-obvious composition

A BeforeModel hook can legitimately use `host.model.complete`. In the two-helper case, both model calls independently finish inside their own 400 ms deadline and the workflow remains inside its 6000 ms turn deadline. Their combined time exceeds the outer request's 400 ms deadline, which has been ticking throughout the hook but was not being awaited. The main model then fails without being sent.

The existing outer deadline may intentionally include the hook, or it may intend to limit only provider work. The inconsistency is independent of that design choice: currently hook time **counts** against the deadline but is **not interruptible by that deadline**. Either include the hook and enforce cancellation promptly, or start the provider-only deadline after the hook. Simply increasing a timeout conceals this boundary rather than resolving it.

## Causal code path

1. `BoundModel::stream` creates the deadline before calling `stream_with_deadline`: [bound_model.rs:372–383](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model.rs#L372-L383).
2. `stream_with_deadline` awaits `apply_before_model` outside its timeout select. Only afterwards does it create and journal an exchange: [bound_model.rs:298–314](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model.rs#L298-L314).
3. The first actual wait on the expired model deadline is the biased select immediately before `service.start_prepared`: [bound_model.rs:320–343](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model.rs#L320-L343). This explains zero main-provider HTTP requests.
4. `RuntimeHookChain` observes operation/turn cancellation, not the enclosing BoundModel deadline: [execution_hooks.rs:63–68](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/execution_hooks.rs#L63-L68), [execution_hooks.rs:97–116](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/execution_hooks.rs#L97-L116).
5. The helper calls run with auxiliary origin and get their own BoundModel deadlines; auxiliary origin skips recursive BeforeModel hooks: [extension_operations.rs:32–49](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/extension_operations.rs#L32-L49), [bound_model/hooks.rs:17–20](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model/hooks.rs#L17-L20).

## Durable facts and limits

The slow-hook case records an accepted BeforeModel trace, then a model request and an immediate typed `Other` failure with `model request timed out after 400ms`, and finally an error turn settlement. `usage_summary` shows an error direct request with near-zero journal duration, although the hook already consumed 1.2 seconds and no provider HTTP occurred. This is diagnostic fallout from the same boundary, not a separate accounting defect.

The two-helper case correctly preserves both completed auxiliary exchanges and their supplied token usage (123 input, 45 output each). No hidden/lost auxiliary usage was found. The direct exchange is error/usage=null. Workflow timeout control leaves no direct exchange, settles as timeout, and delivers hook cancellation. No indefinite process hang, live-provider billing, GUI issue, or stock-profile frequency is claimed.

## Fix direction

Choose and document a consistent scope for `runtime.model_timeout_ms` around BeforeModel. If hooks belong to the model call's time budget, enforce that deadline while awaiting them and propagate an invocation-local cancellation token to hook work and nested callbacks. Do not cancel sibling model executions or the whole turn accidentally. Preserve accepted hook/auxiliary journal facts and avoid attributing an unsent request as provider work. If the documented intention is provider-only, create the main deadline after the hook instead. Keep workflow and explicit hook-export timeout semantics distinct.

No production implementation or PR was created by this audit. The evidence is intentionally independent of module IDs.

## Verification

- `python3 -B run.py`: 11 complete local process cases.
- `python3 -B verify.py`: all captured observations and controls pass, including native HTTP counts, canonical journal settlements, usage rows, hook cancellation and independent helper durations.
- `python3 -B verify.py --expect-consistent`: intentionally fails the desired consistency check on current HEAD. This is a captured-output regression checker, not a production patch or a green correctness test.
- Existing compiled Core targeted suites: model deadlines **9 passed**, execution hooks **4 passed**, extension operations **8 passed**, total **21 passed / zero failed**. Exact commands and executable hashes are included. These were run without rebuilding and are not a full workspace gate.
- Test-only Python scripts compile; production working trees remain unchanged. Existing executable provenance is retained rather than claiming a fresh build.
