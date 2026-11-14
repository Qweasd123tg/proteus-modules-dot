# Proteus Core: cancellation race review

Source revision: `89997df995df7c39b713e16aba216ecb19c8f497` (main rechecked during review).
Production code was not modified. `repro-tests.patch` adds review-only tests in an isolated checkout.
No remote changes, live model requests, credentials, or user working data were used.

## 1. In-flight callback + targeted cancel resets independent sibling

Confirmed by an executed Rust test using the repository's real Python multiplex worker.

The worker emits a legitimate `host.context.build` callback for invocation A. Before
processing this already-received frame, the host processes cancellation of A. This
is a valid interleaving: broker ticks drain controls before inbound worker frames,
and the two directions of stdio do not form a shared total ordering. The test then
handles the callback. The broker treats it as a protocol violation, terminates the
whole component generation, and settles an independent active invocation B as
`ComponentLost(Protocol)`.

Observed diagnostic:
`callback m:1:1 arrived after parent h:1:1 was canceled`

The test asserts the defect's observed behavior; its passing status is confirmation,
not a regression test showing correct behavior. Expected corrected behavior would
reject the late callback with cancellation without executing it or resetting B.
Malformed IDs, forbidden authority, genuinely stale terminal references, and a
cancel-grace timeout should retain their separately justified error handling.

Sources:
- [control-before-frame order](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/runtime.rs#L39-L75)
- [host marks cancellation before notification delivery](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/failure.rs#L156-L184)
- [late callback resets generation](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/routing.rs#L151-L157)
- [failure settlement for siblings](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-module-protocol/src/v3/failure.rs#L272-L299)

Reproduction command after applying the test patch:

```sh
cargo test --locked -p proteus-module-protocol --lib audit_inflight_callback_cancel -- --nocapture
```

Impact: canceling/timing out one call can abort unrelated work sharing the same
component process. This is most relevant to multi-export or concurrently shared
components; it is not a cross-process authority escape.

## 2. Late cancel discards success after success settlement

Confirmed at the direct `AgentRuntime` API and durable journal boundary. A single
root turn, with no queued follow-up, finishes its workflow successfully. The
`TurnSettled(Success)` notification is paused in a best-effort cleanup hook. The
caller cancels while that hook is running, then releases the hook. The runtime
writes a successful canonical settlement with the final output and returns an
error instead of that output:

```text
returned error=turn canceled by client, persisted status=Success,
output=Some(AgentOutput { text: "done", metadata: Null })
```

Cleanup hooks intentionally use a fresh token, so the cancellation does not abort
the notification. After the hook and canonical append, `run_reserved_chain`
checks the original token and converts the successful result to an error.
App-server's corresponding code maps this error plus the canceled token to
`AppRunStatus::Canceled`; that mapping was inspected, not separately driven via
HTTP/UI in this reproduction.

Impact: a caller loses the returned successful result and sees cancellation,
while hooks and cold canonical history say success. A retry based on the returned
error may repeat already successful work. No rollback of completed effects is
claimed. Severity is lower than finding 1; a run chain and an individual turn are
distinct concepts, but this reproduction deliberately contains just one turn and
no queued follow-ups. If run-level cancellation winning during final cleanup is
intended, it needs an explicit contract that preserves and communicates the
completed output, rather than an ambiguous turn-canceled error.

Suggested correction: define a single completion/cancellation linearization
point. Once success wins and terminal cleanup is notified of success, return that
completed output; cancellation should only suppress not-yet-started follow-ups.
Alternatively, if cancellation wins before commitment, publish that consistent
terminal status to hook/journal/client. Do not implement rollback of effects.

Sources:
- [success calculation and terminal hook](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/turn.rs#L204-L226)
- [canonical success append](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/turn.rs#L247-L254)
- [late cancellation overwrites returned success](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/turn.rs#L119-L122)
- [cleanup has independent cancellation token](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/execution_hooks.rs#L63-L68)
- [app-server error mapping](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/runs.rs#L205-L217)

Reproduction command after applying the test patch (the repository's reference
module test fixture must be built/configured as for other Core unit tests):

```sh
cargo test --locked -p proteus-core --lib audit_cancel_during_settled_hook -- --nocapture
```

Both custom tests deliberately assert the observed defect and pass when it is
present. Before using them as regression tests, change assertions to the desired
correct behavior.

## Baseline and scope

The existing integration test `targeted_cancel_keeps_sibling_and_generation`
passes unchanged. It does not test a callback crossing the cancellation boundary.
The focused reproductions used Rust 1.95.0, temporary session storage, a real
Python fixture for the broker, and test-only workflow/hook implementations for
the Core API/journal test. No live LLM requests were made. This is a targeted
concurrency review, not a claim that the entire repository is bug-free.

Full `cargo test --locked -p proteus-module-protocol` also passed: 50 unit tests
(including the added defect reproduction), 21 broker integration tests and 1
startup-deadline test. Therefore 71 existing tests passed alongside the broker
reproduction. The separate Core late-cancel reproduction passed once; the full
Core suite was not run by this reviewer. Compiler reported only two pre-existing
unused helper warnings in profile-watch polling test code.
