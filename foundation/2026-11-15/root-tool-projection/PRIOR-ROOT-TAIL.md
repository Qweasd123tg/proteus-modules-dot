 Reconnect silently loses the tail of a root tool result

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

