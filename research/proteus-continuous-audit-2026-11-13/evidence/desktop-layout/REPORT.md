# Desktop UX audit round 5: navigation and pane persistence

Date: 2026-11-13. Desktop HEAD and remote `main` verified as **75bf201764278eac4b50d156650edcf1429101ff** before and after investigation. No production edits, commits, publication, live account/model calls, or native GPUI window run. All new files are under `audit-round5/`; tracked `git diff` is empty.

## D5-1. Keyboard/pane navigation does not cancel delayed project navigation [P2]

### Concrete workflow

1. With two open tabs/panes, select a project whose session-list request is still pending.
2. Before its response arrives, switch tabs via Ctrl+Tab, focus the adjacent pane via its shortcut, or click the other pane's content.
3. The old project's successful response is still accepted and opens that project, replacing the user's later destination.

The relevant slow request is `src/ui/projects.rs:35-79`; Proteus always requests sessions here, while the direct Codex path requests them when the selected project's latest main chat is not already known. This is not a claim that every project click waits or every keyboard operation races.

### Cause and source

- [`step_tab` and `focus_neighbor`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/mod.rs#L345-L372) do not call `invalidate_navigation`.
- [`focus_pane`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/mod.rs#L339-L343) likewise changes the focused pane without invalidating pending navigation. It is called by the pane mouse-down listener at `src/ui/tabs/view.rs:276-278`.
- [`finish_project_navigation`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/projects.rs#L82-L102) relies exclusively on `navigation_generation` to reject an obsolete request.
- The shared `update_tabs`, `sync_chats`, and focus helpers do not increment that generation either. Explicit tab activation/open/settings/close paths do invalidate, so mouse-clicking a tab label behaves differently from keyboard switching or clicking pane content.

### Executable evidence and boundary

`make_navigation_probe.py` extracts the complete production `step_tab`, `focus_neighbor`, `focus_pane`, `finish_project_navigation`, `invalidate_navigation`, and `latest_main_session` functions. It changes only visibility for placement in the stand-alone crate. `navigation-extraction.json` records exact source ranges and extracted-body hashes. The real unchanged `proteus-tabs` crate implements layout transitions.

The probe replaces GPUI Context/Window, notification/focus/RPC effects and unused Workspace fields with small stand-ins. `update_tabs` applies its supplied closure; its production body was separately inspected to establish that omitted effects do not invalidate navigation. `open_chat` records that the stale callback was accepted. Therefore these are exact-method control-flow reproductions, not native UI or real HTTP race reproductions.

- `navigation-before.log`: **1 control passed, 3 regression expectations failed**, exit 101. All three actions really select `codex:b` before the delayed callback; afterward `open_chat(Codex("delayed-project"))` has been called.
- The control explicitly invalidates the old generation and verifies no `open_chat` call.
- `candidate-navigation.patch` adds invalidation to the three paths, not applied to production.
- `navigation-fixed/` tests that candidate on the extracted methods: **4/4 passed**, `navigation-after.log`. No claim that the full GPUI suite or real-window interaction passed.

Suggested production follow-up: apply the minimal generation fix with actual Workspace entity regressions, cover mouse/keyboard parity and pending chat-creation tickets, then exercise a delayed request in a native window. Moving/splitting tabs should be reviewed under the same explicit-navigation policy, but are not added as separate confirmed findings here.

## D5-2. Collapsing a locked nested layout persists invalid tabs and can reset preferences on restart [P2]

### Minimal deterministic sequence

Open four ordinary documents A/B/C/D in one pane, then:

1. Split B below A.
2. Split C right of B.
3. Split D below B.
4. Lock B's size.
5. Close D. The now-empty slot below locked B is legitimate and layout validation succeeds.
6. Close C. Collapsing its parent exposes the inner column to the outer column. They merge, but the empty D slot survives even though A now supplies the weighted/resizable sibling B needs.

This is 10 actions counting the four opens. `minimal_layout.rs` uses only public production `TabLayout` APIs and a 1200x900 layout. It checks that the penultimate state is valid, then expects the final state to be valid. Actual final result is `Err("an empty pane is next to chats or documents")`. The surviving content tabs are A and B; a third, empty pane remains in the authoritative model. Three repeats fail identically with exit 101 (`minimal-repeat-1.log` ... `-3.log`).

### Root cause

[`Node::normalized`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/crates/tabs/src/tree.rs#L219-L267) decides to retain the inner placeholder while its original siblings are still all fixed. A later single-child collapse and same-axis merge reparent the placeholder beside a weighted ancestor sibling. Its necessity is not re-evaluated. The resulting state violates `TabLayout::validate`, `crates/tabs/src/layout.rs:76-84`.

This was discovered by a deterministic 12-operation layout-state generator. It stopped at seed 1632, step 193 after **815,694** operations, not the planned 2,000,000. The long trace was reduced first by delta debugging and then manually to the 10-action fixture above. Fuzzing is not a proof of general correctness or native UI coverage.

### Why this is more than a visible extra pane

- [`Workspace::update_tabs`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/mod.rs#L43-L60) normalizes the layout **before** the requested close, then saves the close's invalid result into spaces, `self.layout`, and window preferences.
- `WindowGroup::persist` / `Group::saved_layout`, `src/ui/workspace/windows.rs:261-311`, preserve the first window's saved layout without repairing it. One native window is sufficient.
- `preferences::save_at` serializes without validation (`src/preferences.rs:670-680`).
- [`tab_layout`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/tabs/mod.rs#L32-L40) normalizes a **clone for rendering**. Therefore the screen can look normal while the saved model is invalid. This report does not claim the empty pane necessarily remains visible in native rendering.
- [`preferences::load`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/preferences.rs#L575-L598) rejects the entire preferences file for an invalid layout and moves it aside. `src/ui/prefs.rs:76-80` falls back to `Preferences::default()` on that error.

**Timing condition:** the user quits/restarts after that state is saved and before another `update_tabs` (including an arriving session refresh) repairs and re-saves it. A later layout operation can heal it. No claim that settings reset every time this sequence is performed.

### Persistence reproduction

`probe/src/bin/preferences_restart.rs` includes the complete, unchanged production `preferences.rs`, `shortcuts.rs`, `recent.rs`, and `sessions.rs` files by path, and depends on the unchanged real `proteus-tabs` crate. Unused transport/catalog types are small schema stand-ins; the exercised tabs/theme/view data, validation, serialization, save/load and backup filesystem paths are actual production code. No GUI/global writer thread is modeled. Only a fixture-local XDG_CONFIG_HOME inside a fresh process is used.

`preferences-restart.log`, exit 0, verifies the **current defect**:

- Before the final close, save/load retains **Light, scale=125**.
- After the final close, live layout is invalid while an independently rendered/retained clone validates.
- Saving succeeds. Loading rejects the invalid layout and renames the file to `preferences.json.broken-...`.
- The following load returns **Dark, scale=100, no tabs**.
- The broken file is retained, so this is a reset with a recoverable backup, not proved irreversible data loss. Document files and chat histories are not deleted by this fixture.

Suggested repair: reconcile placeholders against their final siblings after collapses/flattening, preserving locked sizes and focus. Add the public-API regression and save/load coverage. Repairing only the render clone is insufficient; blindly adding a second normalization pass should be tested against deeper alternating-axis trees rather than assumed complete. No model-fix patch is presented as production-ready.

## Baseline and reproducibility

- `tabs-unit/` points its library path directly at actual `crates/tabs/src/lib.rs`: **62 existing tests passed**, `tabs-baseline.log`.
- Tracked source tree unchanged, candidate patch is a file only.
- Rust 1.95.0; each probe family has a private target directory. No stale shared-target test reuse.
- Full native Desktop, live HTTP server, rendering/keyboard delivery, paid models and portable build were not run.
- `coverage.tsv` records exact read ranges and file SHA256. Much is cross-boundary rereading of earlier audited areas; do not count it as wholly new repository coverage.

From the repository root with the prepared Rust toolchain:

```sh
python3 audit-round5/make_navigation_probe.py
CARGO_TARGET_DIR="$PWD/audit-round5/target" cargo test --offline --manifest-path audit-round5/probe/Cargo.toml --lib
CARGO_TARGET_DIR="$PWD/audit-round5/target" cargo run --offline --manifest-path audit-round5/probe/Cargo.toml --bin minimal_layout
CARGO_TARGET_DIR="$PWD/audit-round5/target" cargo run --offline --manifest-path audit-round5/probe/Cargo.toml --bin preferences_restart
CARGO_TARGET_DIR="$PWD/audit-round5/unit-target" cargo test --offline --manifest-path audit-round5/tabs-unit/Cargo.toml
CARGO_TARGET_DIR="$PWD/audit-round5/fixed-target" cargo test --offline --manifest-path audit-round5/navigation-fixed/Cargo.toml
```

The first two baseline reproductions are expected to fail on the pinned defective source. The preferences executable exits zero because it asserts the observed defect and its backup/default behavior.
