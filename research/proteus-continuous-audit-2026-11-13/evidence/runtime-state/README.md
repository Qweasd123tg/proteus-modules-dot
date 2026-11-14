# Proteus runtime state linkage audit

Scope: Core main `89997df995df7c39b713e16aba216ecb19c8f497`, verified local and upstream HEAD. Test-only isolated checkout: `/workspace/shared/runtime-state-link-audit`. No production edits, commits, pushes, or PRs.

## RSL-1: completed background child survives successful clear (P2)

User scenario: parent spawns a collaboration child; child completes; user clears conversation; reopening/subscribing to that same warm session still restores the old completed child card.

Chain:
- `app_server/runs.rs:104-112`: successful public `clear_history()` clears runtime durable history and invokes `finish_progress(Ok(empty))`, then publishes snapshot.
- `app_server/events/session.rs:214-220`: `finish_progress` calls `finish_parent_turn`.
- `app_server/turn_progress.rs:238-245`: this clears main/submitted/failed input progress but intentionally keeps background children across ordinary turn completion.
- `turn_progress.rs:319-329`: snapshot always appends those children, including completed cards.

The same helper serves ordinary turn completion and whole conversation clear, which require different scopes of reset. In the deterministic test, a persisted parent run creates two canonical messages and a child-card sequence; after actual clear API, canonical history is zero but authoritative reconnect snapshot has one old completed card. No child subprocess or real model used: child events are synthetic; parent runtime and persistent clear path are real. This is a warm projection inconsistency, NOT a claim that cleared canonical content is sent to the model again.

Fix direction: separate whole-conversation reset from parent-turn completion; at minimum clear terminal background cards during `/clear`. Define behavior for still-running children rather than blindly clearing their routing state.

## RSL-2: equal provider call IDs erase one of two child user-input requests (conditional P2)

User scenario: two independent child sessions ask for input while their providers assign the same call ID. This is legal across sessions, but the parent control plane uses an unqualified request ID.

Chain:
- `tools/request_user_input.rs:191-192`: built-in tool uses `call.id` as `UserInputRequest.request_id`.
- `core/agent_control/process/turn.rs:173-188`: child bridge forwards that ID unchanged, only stamps a new origin. Bridge turns transport failure into an empty user answer.
- `app_server/user_inputs.rs:61-86`: pending map inserts by request_id only; second insert drops the first response sender.
- `app_server/events.rs:194-202`: public pending projection similarly replaces first request by bare ID.
- `user_inputs.rs:91-108`: resolving bare ID addresses only the second request.

Deterministic component probe registers two production pending requests with different execution/thread/turn origins and `call_0`. First response channel closes without an answer; pending contains only child 2; response to `call_0` reaches child 2. An answer from an already displayed child-1 card cannot be distinguished from an answer to child 2. This tests production registration/resolution/watch logic, not a real provider/subprocess run; occurrence depends on ID reuse between independent children. It is distinct from the previously reported display-only nested tool status collision, although the missing ID namespace is related.

Fix direction: allocate an app-server-local UUID for every UI user-input request (like approvals), retain correlation to the original requester; alternatively namespace the public/control-plane request ID by origin. Include old watcher and timeout ownership in any fix to avoid stale callbacks addressing a replacement entry.

## Reproduction

Apply `tests.patch` to the pinned Core checkout; use the repository Rust toolchain/test instructions. No external service or credentials needed.

```sh
cargo test -p proteus-core --lib audit_clear_history_retains_completed_background_agent_snapshot --offline -- --nocapture
cargo test -p proteus-core --lib audit_parallel_child_user_inputs_with_same_provider_call_id_replace_each_other --offline -- --nocapture
```

Tests assert the observed bad behavior to make reproduction deterministic. Convert assertions to desired invariant when implementing a production fix. See test logs for executed results; no production patch is included.

## Execution status and limitations

- Both targeted repro tests passed independently on the final test patch.
- Supplemental `cargo test -p proteus-core --lib app_server:: --offline -- --nocapture`: 150 passed, 83 setup failures. All 83 panic sites report the absent `PROTEUS_TEST_REFERENCE_MODULE` binding. These are fixture preparation failures, **not 83 product findings**; this broad suite is not claimed green. No new build of the reference module was attempted.
- Remote main SHA was rechecked after tests and remains the pinned SHA (see `revision.txt`).
- `git diff --check` passes. Only test code is changed.
