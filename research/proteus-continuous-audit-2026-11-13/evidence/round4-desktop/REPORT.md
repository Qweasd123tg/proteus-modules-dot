# Desktop audit round 4: settings and live transcript

## Source and boundary

- Desktop local HEAD and remote `origin/main`: **75bf201764278eac4b50d156650edcf1429101ff**. Reverified before investigation.
- Supporting Core source: **89997df995df7c39b713e16aba216ecb19c8f497**.
- Production source files were not changed. No remote writes, publication, merge, or live user session access.
- `coverage.tsv` records exact file/range/SHA256. New-vs-prior numbers compare round2 and round3 ledgers, not a claim that nobody audited these lines before those rounds.
- Probe imports actual unchanged `src/transcript`, `src/settings`, and existing Codex modules by path. No substitute implementation of the affected reducer.
- Run: `cargo test --offline --manifest-path audit-round4/probe/Cargo.toml -- --nocapture` from Desktop repository, using existing Rust toolchain. In this workspace the existing target directory was reused with `CARGO_TARGET_DIR=$PWD/audit-round3/probe/target`.

## Findings

### D4-1. Live subagent tool history permanently stops admitting new calls after 64 [confirmed functional defect, P2]

Source: `src/transcript/mod.rs:255-275`, `443-474`.

The live reducer adds a child tool only while `tools.len() < MAX_SUBAGENT_TOOLS`. Once the first 64 calls are retained, it still reports `Change::Updated`, but neither evicts an old tool nor inserts the new one. Its later result/approval updates find no corresponding call. This is not just a bounded history: it retains the oldest 64 forever, hiding current activity in long-running agents.

Reproduction (`audit_live_subagent_discards_every_tool_after_first_64`): emit SubagentStarted, then 100 unique, sequentially completed tool calls under that child's thread. The retained card has 64 tools ending in `call_63`; all later 36 completion events produce `Change::None`. No random IDs, race, provider, or network is required.

The server's retained-window behavior is different: Core `crates/proteus-core/src/app_server/turn_progress.rs:480-518` evicts an older non-running tool (falling back to the first) and inserts the latest. Thus a fresh snapshot can replace the card with recent calls, but subsequent live events are dropped again as soon as the loaded window contains 64.

Impact is a stale live UI, not proven loss of persisted child history or execution. Suggested repair: align the live retained-window policy with Core; preserve a bounded set while admitting the latest calls and preserving active ones where possible. Regression should assert latest call visibility after >64 completions.

### D4-2. Child tool completion is routed by call_id without thread identity [confirmed reducer defect; provider collision condition]

Source: `src/transcript/mod.rs:292-305`, `443-474`; caller forwards envelope thread ID at `src/ui/chat/pump.rs:178-180`.

Request events correctly use child thread identity to choose the card. Result, resolved-arguments, terminal-binding and approval events discard that identity and search all rows backwards for the first matching call ID.

Reproduction (`audit_same_call_id_in_different_children_updates_wrong_child`): two running children A and B each request `call_1`; completing A updates B with A's result and marks B done, while A stays running. The test asserts the actual wrong row and wrong result, not just a generic mismatch.

Reachability evidence: Core `core/agent_control/process/turn.rs:73-136,192-205` re-emits child tool events under the child's thread ID without rewriting call IDs. The OpenAI and Anthropic adapter parsers preserve provider IDs (`model/model-pack/src/adapters/openai/response/item.rs:73-87`, `anthropic/response.rs:67-81`). The public CallId type is an arbitrary string. This test intentionally supplies a collision; it does **not** establish its frequency for any hosted model nor claim one occurred in the user's runs. Most globally randomized provider IDs will not collide. Adapters/replay/test providers using per-session counters can trigger it.

Supporting Core TurnProgress is also keyed only by call_id for these updates, so a Desktop-only correction may not be enough to keep later server snapshots consistent. Core was statically inspected, not included in the executable reproduction. Suggested repair: scope live tool identity and event matching by thread (and turn/generation if required), with equivalent Core projection rules.

## Tests

`test-output.txt`: **97 passed, 0 failed, 1 ignored**. This is 95 existing passing tests plus two new reproductions that assert the current broken behavior. These are evidence tests, not regression tests proving a fix. The ignored existing Codex test was not enabled. Full GPUI application and live paid-provider runs were not performed.

## Candidate not promoted to confirmed finding

`src/ui/settings/mcp_editors.rs:190-197` clears every MCP form when any server is removed. Other forms can contain invalid raw text not represented in Draft (`:17-23,124-140`), so removing B appears to discard the invalid edit/error in A and rebuild A from its last valid value. This is static evidence only; no native GPUI interaction test was run. Keep separate from the two executable findings.

The settings draft/schema/reconcile/catalog review and their existing headless tests did not establish another high-confidence bug this round. Some line-based MCP fields normalize whitespace; whether preserving every unusual argv/env value is intended needs a product contract before calling it a defect.
