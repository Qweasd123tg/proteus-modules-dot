# Tool response lifecycle audit, 2026-11-13

Scope: Core tool replies, cancellation, live/reconnect/cold projections. Only diagnostic tests were added in an isolated clone. No production code changed, committed, pushed, or published.

Verified Core main SHA, twice with `git ls-remote origin refs/heads/main`:
`89997df995df7c39b713e16aba216ecb19c8f497`.

## 1. A response to an already canceled approval/question is falsely acknowledged

Suggested priority: P2 correctness. This is not an authorization bypass or evidence of any tool execution after cancellation.

`resolve_pending_approval` removes the entry, publishes ApprovalResolved(approved=true), and returns success once the response is sent to the intermediary watcher. It does not wait for delivery to the actual runtime requester. If that requester has already dropped its receiver, the watcher accepts the intermediary response (biased select) and ignores the failed final send. The cancellation branch never publishes a correction. The exact same chain exists for user-input answers.

Deterministic current-thread Tokio tests use the real register/resolve/watch functions, register a pending request, drop the actual receiver before answering, and answer before the scheduled watcher polls. Both return `Ok(())`, remove the pending entry and publish resolved; approval explicitly publishes `approved: true`. The nonempty synthetic user answer is discarded. Both tests repeat expected-red 10/10. Normal forward and cancel-cleanup controls all pass.

Source:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/approvals.rs#L99-L120
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/approvals.rs#L159-L187
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/user_inputs.rs#L89-L109
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/user_inputs.rs#L142-L168
- HTTP command mapping calls these APIs directly: app_server/http/commands.rs:95-120.

Fix direction: acknowledge actual responder delivery rather than intermediary queue admission. Final send failure must reach caller and not leave approved=true as the terminal published fact. No requirement to await actual tool completion.

Limit: deterministic race at the production API/control-plane functions, not a GUI/manual HTTP end-to-end cancellation run. Does not show lost replies during normal live-requester flow.

## 2. Reconnect silently loses the tail of a root tool result

Suggested priority: P2 display correctness; not durable journal corruption or model context truncation.

`turn_progress::update_tool` applies `MAX_SUBAGENT_TOOL_RESULT_BYTES = 10000` to every tool, including root tools with compact=false. It copies only the prefix and supplies no visible truncation marker or metadata. The Core BoundTools normal result budget is 200000 bytes and intentionally preserves head/tail when truncating, but this secondary projection bypasses that policy.

A synthetic 10017-byte result ends with FINAL_DIAGNOSTIC. Actual RuntimeEventSink + AppEventPublisher + reconnect subscription gives:
- original streaming ToolFinished: 10017 bytes, tail present;
- reconnect SessionSnapshot during live turn: 10000 bytes, tail absent;
- completed canonical-message transcript: 10017 bytes, tail present.
The low-level projection test also checks metadata is null and no truncation notice exists.

Source:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/turn_progress.rs#L5-L8
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/turn_progress.rs#L547-L569
- snapshot consumes progress without recovering the missing text: app_server/events/session.rs:94-107.

Fix direction: keep the already bounded root result unchanged; if truncation is desired for background summaries, explicitly mark it and retain a useful tail. A reconnect should not silently turn a complete visible result into a different one.

Limit: production server event/snapshot and canonical transcript APIs tested, no actual Desktop UI run. Cold comparison uses the canonical-message transcript API, not an on-disk journal/HTTP session. Existing reconnect settlement control passes. Permanent history retains the source content.

## Evidence

- `diagnostic-tests.patch`: four expected-behavior regression tests, tests only.
- `audit-regressions-expanded.log`: 4 expected failures, 0 passes, 726 filtered; confirms both defects and integration path.
- `race-repeat.log`: both cancellation races reproduce 10/10 under the deterministic schedule.
- `baseline-controls.log`: five existing controls pass (two cancel cleanup, two normal response forwarding, one reconnect settlement).
- `git diff --check`: passed.

Reproduce in isolated clone with diagnostic patch:

```sh
source /workspace/shared/proteus-toolchain/env.sh
CARGO_TARGET_DIR=/workspace/shared/proteus-runtime-audit-target \
  cargo test -p proteus-core --lib audit_lifecycle_ -- --nocapture
```
