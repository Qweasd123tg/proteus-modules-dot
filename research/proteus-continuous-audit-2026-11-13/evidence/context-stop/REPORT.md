# Context-window stop becomes a generic length error and repeats paid work

## Scope

- Core remote main: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Modules remote main: `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Both verified through GitHub at the start and end of this pass, 2026-11-13.
- Real Core, process workflow, process compaction hook and native Anthropic adapter; only the HTTP server is a fixture. No external credentials, live provider calls, production edits or publication.
- Modules retain their actual Core dependency pin `b5fac84245b075896c24763b3aebac79b4375c2e`; root Core executable is built from the current main listed above. Binary SHA256 values are in `provenance.json`.

This is **a new HTTP200 path in the earlier Anthropic failure-classification cluster**, not an unrelated duplicate finding. The earlier reproduction covered HTTP400 prompt-too-long and broken SSE streams. Here the provider successfully returns a documented terminal stop reason and actual usage, both of which are lost before recovery.

## Confirmed behavior

When Anthropic returns `stop_reason: "model_context_window_exceeded"`, its native adapter combines that reason with `max_tokens` into canonical `FinishReason::Length`. Core rejects Length as a generic protocol failure. The compactor receives `ModelFailureKind::Other`, so it repeats the **identical full summary request**, rather than entering the existing context-window trim-and-retry branch. After retries the pending user turn fails.

The response's token usage is also discarded: the real `usage_summary` API returns `status: error`, `finish_reason: null`, `usage: null`, even though the HTTP response supplied usage. With the default five retries, this path permits six summary generations before failure. That is a source-based retry count, not six calls measured in this test. Unlike an HTTP400, a context-window stop can occur after actual generation, so repeated attempts may incur repeated provider usage. No money was spent by these fixtures.

### Source chain

1. Native response decoder merges `max_tokens` and `model_context_window_exceeded`: [response.rs lines21-26](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/response.rs#L21-L26); streaming equivalent [stream.rs lines324-340](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/stream.rs#L324-L340).
2. Canonical response validation rejects Length: [canonical_response.rs lines102-104](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/model_standard/canonical_response.rs#L102-L104).
3. The actual BoundModel path converts that validation error to an untyped `anyhow` error and records its `Other` classification before recording a normal response: [bound_model.rs lines484-505](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model.rs#L484-L505). `failure.rs` maps untyped errors to Other. The equivalent direct ModelService path also rejects it; it is not necessary to the process reproduction.
4. Compaction recovery trims history only for `ContextWindowExceeded`; `Other` repeats unchanged history: [recovery.rs lines20-49](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/hook/codex-context-preparation/src/recovery.rs#L20-L49).
5. Usage projection saves finish reason/usage only from a recorded response, not Error: [usage.rs lines46-56](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/usage.rs#L46-L56).

## Reproduction and controls

`run.py` runs ten isolated stdio-server sessions, each with a synthetic workspace. Each is a full process chain, with both native streaming and non-streaming variants. The fixture's first successful response reports input180000/output1, which reliably triggers pre-turn compaction at the default180000 threshold. The fixture text itself is short: **the reported usage is synthetic and this is not a tokenizer test or a real180k-token provider acceptance test**.

For compaction, the local provider sends an HTTP200 completion with input190000/output10000 and the selected stop reason. The returned text is deliberately short. These are protocol fixture counters, not measured billable tokens. `stream_max_retries=1` limits runtime and makes two identical attempts observable.

| Scenario, each in two stream modes | Requests | Result |
|---|---:|---|
| Prior turn, summary `end_turn`, ordinary continuation |3|Both user turns succeed; continuation differs from summary request|
| Prior turn, summary `model_context_window_exceeded` |3|Prior succeeds; two identical summary requests; next turn fails; both failed journal records are Other|
| Prior turn, summary `max_tokens` |3|Same generic length/error classification; distinguishes output exhaustion from window exhaustion|
| Direct `model_context_window_exceeded` |1|User turn fails, not false success; usage/finish reason are absent from usage_summary|
| Direct `max_tokens` |1|User turn fails, not false success; usage/finish reason are absent from usage_summary|

Total: **10 scenarios,22 local HTTP requests**, all observed-behavior assertions pass. The desired-recovery assertion intentionally fails and is retained in `expected-failure.log`.

The normal end_turn control proves the real compactor is configured and can run successfully. The direct controls reject the tempting but false conclusion that a truncated response is being declared successful. They also show that a repair must not indiscriminately label every Length as context-window exhaustion.

## Input/output budget hypothesis, corrected

The actual outgoing requests have `max_tokens:64000`; native capabilities advertise input200000/output64000, and default compaction begins at180000. This is pressure on the available output headroom, **not proof that all requests above136000 input tokens are invalid**.

The current primary [Anthropic context-window documentation](https://platform.claude.com/docs/en/build-with-claude/context-windows) says Claude4.5 and newer accept a request when input plus max_tokens exceeds the window, then use `model_context_window_exceeded` if generation fills it. Older models use a validation error unless opted into the relevant beta behavior. Therefore the blanket reserve-error hypothesis is rejected. The confirmed finding concerns handling of the explicit stop reason, not a claim that a short summary must always exhaust the remaining window.

Also consulted the primary [stop-reasons documentation](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons), which distinguishes output-token exhaustion from context-window exhaustion. References checked2026-11-13. No live provider inference was used.

## Repair direction

Preserve the provider distinction at the native Anthropic boundary so `model_context_window_exceeded` can reach context-window recovery; keep ordinary `max_tokens` distinct. Do not parse provider-specific strings in the workflow, do not run incomplete tool calls, and do not mark a truncated response successful. Preserve observed usage/terminal cause separately from success validation so failed generated answers remain measurable. Add the real process test with successful-summary and output-limit negative controls.

## Verification

```bash
python3 /workspace/shared/context-stop-chain-evidence/run.py
python3 /workspace/shared/context-stop-chain-evidence/verify.py
# Intentional regression assertion:
python3 /workspace/shared/context-stop-chain-evidence/verify.py --expect-context-recovery

source /workspace/shared/proteus-toolchain/env.sh
cd /workspace/shared/proteus-review-20261112/core/target/sources/modules
python3 scripts/test.py -p codex-context-preparation -p model-pack --offline
```

Baseline: **22 compactor +158 model-pack tests passed;0 failed**. This is focused coverage, not a full workspace gate. No production fix or fix-validation claim is made. Evidence includes captured provider requests, app-server events, durable journals, usage_summary responses, configs, logs and binary hashes.
