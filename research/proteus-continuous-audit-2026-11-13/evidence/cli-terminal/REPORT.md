# Interactive CLI background questions and shutdown lifecycle

Date: 2026-11-13. Core remote `main` checked before and after reproduction:
`89997df995df7c39b713e16aba216ecb19c8f497`.

This is an independent functional repro, not a repetition of the earlier late-approval correlation bug. No repository production files were modified. It uses the clean production CLI executable built for this HEAD, a deterministic model-free workflow component, the repo's local allow-all **test fixture policy**, and one actual spawned Proteus process. No live provider, credentials, or network requests are used by the scenario. All working sessions and markers are isolated in `/tmp/proteus-cli-idle-*`.

## Confirmed: background collaboration input is invisible while REPL is idle

1. Interactive root workflow invokes `spawn_agent` and returns normally.
2. The child sleeps 800 ms and invokes the actual built-in `request_user_input`.
3. CLI is already back at its ordinary `❯` prompt. For the next 3 seconds it never displays `BACKGROUND_QUESTION` or `SELECT_BACKGROUND_ANSWER`.
4. The child is still blocked waiting for input.
5. Sending the unrelated `/history` immediately displays the pending child question. Entering `1` correctly delivers `Alpha` to the child.

This is not an unavailable child input transport: the successful response is verified in the child's tool result. `wait-result.txt` and `wait-transcript.txt` contain the evidence.

With `approval_timeout_ms=1200`, the same background question is never displayed before expiry. The child receives `ok: true`, `output: "User did not provide answers."`, `answers: {}`, `duration_ms: 1204`. Only afterward does `/history` display the expired question. `timeout-result.txt` proves the child had already received the empty response before any question appeared in the terminal.

### Cause

- [`main.rs:538-560`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/main.rs#L538-L560): idle REPL synchronously blocks on stdin. It does not poll app-server output.
- [`cli_app.rs:163-191`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_app.rs#L163-L191): app-server events are consumed only within a foreground request's response loop.
- [`cli_app.rs:208-230`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_app.rs#L208-L230): old Requested events prompt synchronously; Resolved events are ignored.
- [`user_inputs.rs:125-143`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/user_inputs.rs#L125-L143): parent timeout correctly completes pending request with an empty response, irrespective of CLI not having displayed it.

Impact: background child interaction can stall silently until the user happens to submit another command, or time out unanswered without the user ever seeing the question. The latter can subsequently expose the already-known control-response desync, but that is not counted as a new issue here.

## Confirmed linked lifecycle consequence: `/exit` opens old child prompt and exceeds shutdown deadline

Same pending background question, but the user enters `/exit` instead of `/history`:

- CLI displays the queued child question after the exit command.
- CLI remains alive and waiting for an answer for at least 4 seconds, although its shutdown deadline is 2 seconds.
- Entering `1` finally releases it, and CLI exits with `write app-server request: Broken pipe (os error 32)`.

Evidence: `shutdown-result.txt` (`alive_after_4_seconds=True`) and `shutdown-transcript.txt` (exit command, late question, broken-pipe error).

The precise additional cause is [`cli_app.rs:118-132`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_app.rs#L118-L132): shutdown reuses the ordinary request/event handler inside `timeout_at`. [`prompt_user_input:361-362`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_app.rs#L361-L362) performs a blocking stdin read inside that future, so Tokio cannot interrupt this poll at the deadline. This is an observed four-second overrun, not a measured infinite-duration claim.

## Run

```sh
python3 /workspace/shared/cli-terminal-evidence/probe.py wait
python3 /workspace/shared/cli-terminal-evidence/probe.py timeout
python3 /workspace/shared/cli-terminal-evidence/shutdown_probe.py
```

Each script asserts the important observations and bounds cleanup of its own process group. `*-workspace.txt` identifies its retained local temporary session for further inspection.

## Fix direction, not yet implemented

Have an independently running app-server reader/dispatcher and nonblocking terminal input, so events continue to be processed while the composer waits. Maintain pending prompt lifecycle and dismiss/skip already-resolved questions. Once shutdown is requested, drain and correlate responses without starting a new interactive prompt. PTY coverage is required: the existing noninteractive shutdown tests cannot exercise synchronous terminal input.
