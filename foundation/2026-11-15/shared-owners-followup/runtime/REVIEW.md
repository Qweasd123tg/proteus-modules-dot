# Independent review: running mailbox delivery extraction

Reviewed exact patch SHA-256:
`a43ec06b39a78e1abf8adda2eafc78c332a1c95a0e60b29bfb55909ac234ecde`.
Base: Core `9437c61785cdb5933a980e7d683afb7e85f352e9`, independently rechecked
as current main. Independently fetched `message.rs`, `control.rs` and the
agent-control contracts at that commit; their Git blobs and local bytes match.

## Verdict

No blocking source-level correctness defect found. This is a bounded private
helper extraction, not a routing/lifecycle fix or measured performance win.
Suitable to carry as a reviewed source-only candidate, **not compile/test or
production-adoption approval**. No publication was performed.

## Routing and admission

`SendMessageTool` still calls `running_agent(session_id, target)` and
`FollowupTaskTool` still calls `begin_followup(session_id, target)` before the
helper. These methods have different idle/reservation/capacity behavior and
were not merged. The helper parses `running.path`, builds the same root-origin
typed message, and sends through the saved `running.owner` with the exact saved
`running.handle`. It does not route through the current host, resolve an owner
again, select a new generation or spawn a replacement. A child finishing after
lookup remains the same pre-existing send race; no retry or fallback is added.

The entire idle-followup branch, including reservation, abort paths, attach,
spawn monitoring and cancellation, was independently compared byte-for-byte
and is unchanged. `required_message` is also byte-identical.

## Error and result semantics

- Address parse and receipt serialization errors still propagate as `Err`.
- Envelope validation errors remain successful outer results containing
  `tool_error` with `error.to_string()`.
- Backend send errors remain `tool_error` with full `{error:#}` formatting.
- The extracted return inside the old running match arm has the same outcome:
  that match is the outer invoke's tail expression and no subsequent work is
  bypassed or newly executed.
- Explicit operation literals remain `send_message` and `followup_task`, not
  user-controlled `call.name`. Call ID and tool metadata remain unchanged.
- Success still serializes the same target, `Queued`, `turn_started=false`
  and `generation=None` (omitted on the wire by its existing serde rule).

## Ownership and async boundary

The helper borrows `RunningAgent`; the caller retains its path, saved owner
Arc and handle. Control methods already return cloned owner/handle values and
release their mutex guard before this await. There is no added lock, clone,
spawn, state write or await inside the sequence. `from_root` still performs
the one owned message-text construction before sending.

Borrowing the whole RunningAgent across await requires its members to be
Sync. Source definitions support that: the path is String, the owner trait is
Send + Sync, and the handle was already shared-borrowed across the same await.
No custom destructor or new ownership transfer is introduced. This source
argument is not a substitute for Rust compilation; generated future layout,
stack traces and optimizer effects are not claimed identical.

## Independent checks and remaining coverage

Strict whitespace apply-check, zero-fuzz/no-offset actual apply, exact match
with the proposed after file, reverse-check and exact baseline restoration
passed independently. The selected patch changes only one file, +29/-39.

The existing running-send/followup test covers both entrypoints, no extra
spawn, turn_started and content; its TestHost discards the actual handle and
message envelope. Therefore it does not independently prove saved-owner,
handle, envelope/error or metadata routing. The idle followup test covers a
different boundary and should remain. No tests were removed by this patch.

Rust/Cargo/rustfmt are absent here. No project tests, real peers, replay,
benchmarks or CI were run. Before adoption, run the supported affected
collaboration lib target and applicable peer evidence under the repository's
testing matrix. Do not substitute these source/apply checks for those results.
