# Desktop user workflow / profile inheritance audit

Date: 2026-11-13. No publications, merges, production source edits or live model calls.

## New confirmed finding: new launch-project chat does not inherit last session settings (P2)

**User workflow:** launch Desktop in project A; run a nonempty main chat in A; change its session-local mode to Plan while the published profile remains Normal; create another chat in A. The new chat starts in Normal rather than inheriting Plan. Performing the corresponding action in project B inherits Plan. If the active chat is still blank, Desktop reuses it; this report concerns new chat creation, not blank-chat reuse.

This is a behavioral inconsistency with the documented contract at Desktop `README.md:325-327` and `src/ui/projects.rs:1-2`: new chats inherit settings from the project's latest session. It is not a claim that Core's no-source behavior is wrong: Core correctly uses the published launch profile when no source was requested.

### Causal chain

1. Desktop `src/ui/projects.rs:149-151` returns early for `project == self.workspace_path`, calling `start_chat(None, None, ...)`.
2. Other projects go through the latest main Proteus session selection at `projects.rs:152-162`.
3. `start_chat` sends that optional source to `api.new_session`.
4. Core `crates/proteus-core/src/app_server/http/lifecycle.rs:54-77` copies the session-local mode only when `source_session_dir` is present. With no source it uses the published launch profile.

### Reproductions

- `ui_probe.rs` compiles the complete actual `new_chat_in` method extracted from the pinned Desktop source, with only `pub(super)` changed to `pub` for placement at crate root. GPUI, active-blank-chat handling and RPC effects are stubbed. The actual method's source filtering, branch and path canonicalization execute. Observed: launch project `source=None`; other project `source=Some(last-session)`. **1 passed**.
- `core-repro.patch` adds one isolated test to actual Core. It creates a source session in Plan with its profile in Normal and invokes the real `execute_new_session` twice. Observed: `launch_folder_branch: Normal`, `other_folder_branch: Plan`. **1 passed**, log `core-output.txt`.
- Existing Core controls `lifecycle_uses_the_explicit_source_workspace_and_keeps_deletion_in_the_config_store` and `new_session_loads_published_profile_before_starting_components`: **2 passed**.
- `ui_regression.rs` expects last-session inheritance for both projects: **fails on current source (exit 101)**. `ui_regression_fixed.rs` applies the candidate removal of the early return: **passes (exit 0)**. Logs saved before/after.

Candidate fix `candidate-new-chat-inheritance.patch` deletes only the three-line launch-project special case. It has not been applied to the working repository or published. A production-quality PR should extract/test the source-selection helper in the actual Desktop suite and run the relevant UI suite. This audit does not claim live GPUI/native-window reproduction or a full Desktop suite pass.

### Versions and setup

Remote `refs/heads/main` were rechecked and matched local sources:
- Desktop `75bf201764278eac4b50d156650edcf1429101ff`
- Core `89997df995df7c39b713e16aba216ecb19c8f497`

Core used the official reference process fixture already built from clean Modules `3270dc0f894eaf4d0360306052b806099b8f5351`. The first invocation omitted `PROTEUS_TEST_REFERENCE_MODULE` and failed fixture setup; it was rerun successfully with that explicit binding. This setup failure is preserved separately and is not a product finding. A private build target was used after the shared target was occupied.

Reproduction commands:

```sh
python3 evidence/make_ui_probe.py
CARGO_MANIFEST_DIR="$PWD/evidence" rustc --edition 2024 --test evidence/ui_probe.rs -o evidence/ui_probe
evidence/ui_probe --nocapture
# Apply core-repro.patch to an isolated Core checkout at the SHA above:
PROTEUS_TEST_REFERENCE_MODULE=/path/to/proteus-reference-module \
  cargo test --offline -p proteus-core --lib \
  audit_new_chat_explicit_source_preserves_session_mode_but_none_uses_profile -- --nocapture
```

## Additional review and rejected hypotheses

- Read attachment generation guards, saved drafts and restoration, session creation routing, settings save/dismiss/revision/context boundaries, user input reply handling, pane history/transfer/retarget state, and per-chat retained workspace routing. Read ranges and content hashes are in `coverage.tsv`. This is scoped coverage, not a claim that the whole repository was read.
- Apparent stale-settings-save destination race was not confirmed: SettingsContext belongs to a view and close/navigation guards prevent leaving a saving/dirty settings view.
- Apparent inability of back-navigation to cross root-chat areas is not reported: `SpaceViews` explicitly stores separate navigation histories per retained root, and `take_space_views`/`restore_space_views` transfer that history with the area.
- `include_window` duplicate pinned-state behavior was not established as an ordinary UI bug: native window routing has ownership checks preventing duplicate tabs in the same root. No report without a reachable workflow.
- Did not repeat previous Feedback correlation, Codex pagination/resync, catalog receipt/state, profile include resurrection, subagent card, extension rendering, provider serialization, or cancellation findings.
