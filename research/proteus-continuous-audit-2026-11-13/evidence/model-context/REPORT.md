# Native Anthropic errors break two recovery paths

## Scope and source identity

- Modules remote main checked 2026-11-13: `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Core remote main checked 2026-11-13: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Tests use Modules' actual Cargo dependency pin, Core `b5fac84245b075896c24763b3aebac79b4375c2e`; no dependency substitution.
- Clean isolated checkout: `/workspace/shared/model-context-chain`. Only test files/dev-dependencies changed. No production changes, commits, pushes, external provider calls, or real credentials.
- One underlying defect cluster: native Anthropic failures lose actionable `ModelFailureKind`. Two independently demonstrated user consequences below. This is not a repeat of previous image/tool argument serialization findings.

## M4a: prompt-too-long never reaches compactor's trim-and-retry branch

**Confirmed, high confidence.** On Anthropic context-window exhaustion, native streaming and non-streaming clients return an untyped error. The model-module boundary wraps it as `Other`. `codex_compact` therefore repeats the same oversized history rather than removing old items. Once retry budget is exhausted, compaction and the pending turn fail.

Source chain:

1. `model/model-pack/src/adapters/anthropic.rs:197-201` turns non-success HTTP response into plain `anyhow!`; `:212-214` uses `error_for_status()` on streaming requests, additionally losing the response body.
2. `model/model-pack/src/module.rs:146` and contracts `model_standard/failure.rs:53-59` map untyped errors to `ModelFailureKind::Other`.
3. `hook/codex-context-preparation/src/recovery.rs:22-46`: only `ContextWindowExceeded` removes oldest message and paired tool items. `Other` retries unchanged history.

### Reproduction and control

`audit_anthropic_overflow_prevents_real_compactor_trimming` runs the real compaction algorithm and native Anthropic client, with Core's actual RequestShaper, against a loopback HTTP fixture. The fixture returns the documented HTTP400 `invalid_request_error` / `prompt is too long` response while history contains an old marker, and succeeds when it is removed.

With `stream_max_retries=1`:

| Path | Provider requests | Provider message counts | Result |
|---|---:|---|---|
| native non-stream | 2 | 3, 3 | Other, compaction fails |
| native streaming | 2 | 3, 3 | Other, compaction fails; cause text absent |
| diagnostic control, same non-stream client, only failure kind corrected | 2 | 3, 2 | summary accepted, compaction succeeds |

The control does not modify production code; it proves the recovery branch already works once the correct classification reaches it. Message counts are provider-serialized counts: adjacent user items are coalesced. Assertions also compare the entire failed provider message arrays, not only counts. At the default retry budget5, source logic gives6 unchanged attempts; the test uses1 to avoid unnecessary waiting.

**User effect:** a long conversation can stop at a point where automatic compaction should recover. In the default streaming profile, even the useful provider diagnosis is hidden behind a generic400 URL error.

**Limits:** the fixture deliberately does not allocate/send200k real tokens and is not a live-provider acceptance test. It tests native HTTP error propagation and recovery on the documented response. Full process launch/desktop UI were not exercised.

## M4b: an established Anthropic stream cannot use configured Codex reconnects

**Confirmed, high confidence.** Native Anthropic marks both premature SSE EOF and an explicit transient `overloaded_error` as `Other`. `coding.codex_loop` reconnects only on `StreamDisconnected` or `Retryable`, so a configured retry budget of5 is bypassed and the turn ends after its first model request.

Source chain:

1. `model/model-pack/src/adapters/anthropic.rs:244-257`: transport errors and EOF without terminal event become `Other`.
2. `model/model-pack/src/adapters/anthropic/stream.rs:248-256`: error event extracts only its message; provider error type is discarded and every error becomes `Other`.
3. `workflow/coding-workflow/src/codex_sampling.rs:68-74`: `Other` exits immediately.

### Reproduction and controls

`audit_anthropic_eof_and_overload_skip_configured_codex_reconnect` gets failures from the real native client over loopback HTTP. Each SSE fixture first emits a real `TextDelta("visible partial")`, then either closes without `message_stop`, or sends a documented `overloaded_error` event.

The actual returned `ModelFailure` is serialized/deserialized through its contract and supplied to the real `CodingCodexLoopWorkflow` using the existing workflow host test harness:

| Failure | Adapter kind | Configured retry budget | Actual workflow calls | Typed control calls |
|---|---|---:|---:|---:|
| premature EOF | Other | 5 | 1, error | 2, success with StreamDisconnected |
| SSE overloaded_error | Other | 5 | 1, error | 2, success with Retryable |

**User effect:** transient stream trouble requires manual recovery instead of using available reconnects. Merely increasing `stream_max_retries` does not help. This finding does not claim partial text should be replayed as a complete assistant message.

**Limits:** the HTTP adapter is real; the subsequent workflow boundary is an explicit simulated host fed that real serialized failure. This is a linked contract reproduction, not a full provider→worker→Core→desktop end-to-end run. Other host services are mocked. No measured production incidence.

## Rejected candidate / useful negative control

A summary request clears `max_output_tokens`, which might appear to make Anthropic fall back to2048 despite a larger thinking budget. That reading is misleading because Core's RequestShaper fills the adapter's advertised max output64000 before serialization. The actual HTTP test asserts `max_tokens == 64000`; no bug is claimed on this basis.

## Suggested fix direction

Use a native Anthropic failure decoder shared by both HTTP routes and SSE error mapping; preserve the response body before returning HTTP errors. Map known context-exhaustion responses narrowly to `ContextWindowExceeded`, established premature stream termination to `StreamDisconnected`, and known transient overload failures to `Retryable`. Do not classify every400/invalid_request_error as context overflow and do not make the workflow parse provider text. Add the cross-component tests above plus permanent-error negative controls.

## Primary provider references

- https://platform.claude.com/docs/en/build-with-claude/context-windows : input exceeding context returns400 invalid_request_error with prompt-too-long diagnosis.
- https://platform.claude.com/docs/en/build-with-claude/streaming : overloaded_error may appear after an HTTP200 SSE stream begins.
- https://platform.claude.com/docs/en/api/errors : provider error envelope and transient overload classification.

References checked2026-11-13; no long verbatim quotes copied.

## Artifacts and commands

- `reproduction.patch`: test-only additions and their dev dependencies.
- `tests.log`: full focused package suite and audit diagnostic output.

```bash
source /workspace/shared/proteus-toolchain/env.sh
cd /workspace/shared/model-context-chain
CARGO_TARGET_DIR=/workspace/shared/proteus-review-20261112/modules/target \
  cargo test -p codex-context-preparation -p coding-workflow --offline -- --nocapture
```

Validation result: 116 unit tests passed (23 compactor, 93 workflow), including both new audit probes; 0 failures. Test-only patch reverse-application check passed.
