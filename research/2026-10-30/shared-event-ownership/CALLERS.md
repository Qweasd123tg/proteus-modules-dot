## Every raw AppServerHandle.subscribe caller (14)

Paths below relative to `crates/proteus-core/src/`:

- `app_server/acp/prompt.rs:31`
- `app_server/http/state.rs:165`
- `app_server/http/tests/live.rs:7`
- `app_server/http/tests/slash.rs:136`
- `app_server/http/tests/turns.rs:6,72,187,242,334`
- `app_server/profile_watch/tests.rs:95,96,195`
- `app_server/tests.rs:739,881`

Raw publisher subscribers additionally: `app_server/tests.rs:260,323,365,416,454,499,532,598,629,670`; `app_server/events.rs:250` test helper; handle forwarding `app_server.rs:79`. Underlying channel subscription `app_server/events.rs:125`.

## Receiver<AppServerEvent> declarations (9)

- `app_server.rs:78` handle API
- `app_server/acp/prompt.rs:20` ACP field
- `app_server/events.rs:124,248` publisher API/test helper
- `app_server/http/state.rs:65` separate activity channel, not publisher raw receiver
- `app_server/http/tests.rs:221,239` test helper parameters
- `app_server/profile_watch/tests.rs:9,24` test helper parameters

## Publisher send callers

`AppEventPublisher::send` callers, paths relative to `crates/proteus-core/src/`:

- `app_server.rs:133,156,160,168`
- `app_server/approvals.rs:86,111,132,182`
- `app_server/control_plane.rs:79`
- `app_server/http/tests/addressing.rs:163,169,188,194`
- `app_server/http/tests/pending.rs:86`
- `app_server/profile.rs:64,78`
- `app_server/read_model.rs:200`
- `app_server/runs.rs:39`
- `app_server/user_inputs.rs:76,101,120,166`

Internal send-with-history callers: `app_server/events.rs:157`, `app_server/events/session.rs:223`. Direct sequenced/raw channel publication pairs: `app_server/events.rs:201,205` and `app_server/events/session.rs:175,179`. Activity-channel send at `app_server/http/state.rs:137` is separate, not an AppEventPublisher call.

