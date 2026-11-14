# Proteus Desktop: project catalog lifecycle and session-list focus

Date: 2026-11-13. Desktop local HEAD and remote HEAD are **75bf201764278eac4b50d156650edcf1429101ff**, checked before and after. No production edits, commits, publication, user data, running backend, live Codex account/model, or native GPUI window. `git diff --stat` remained empty.

## PN-1. A delayed project catalog resurrects a deleted session in the sidebar [P2]

### Sequence

1. Window A starts opening a project. Its Core `/sessions` read, or its Codex `list_until_main` read when the project's main thread is not yet in A's catalog, captures a session that still exists. Hold delivery of that result to the UI.
2. A later destination invalidates A's navigation generation. The session is successfully deleted, e.g. in another window; the ordinary `forget_chats` cleanup reaches A and advances `session_catalog_epoch`.
3. The fresh post-delete catalog has already reached A and does not contain the session.
4. Release the old project result. **The deleted row is added back.** The stale project selection is correctly rejected, but that guard runs only after catalog mutation.

This is resurrection of **UI catalog metadata**, not recreation of the deleted session/history on disk. Subsequent ordinary catalog refresh can clear it; clicking the ghost can attempt resume of an already deleted session. This report does not claim the UI row persists forever or that the server deletion failed.

### Source chain

- [`src/ui/projects.rs:35–79`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/projects.rs#L35-L79): only `navigation_generation` is captured. Codex completion upserts every returned summary at lines 56–60. Core completion calls `set_sessions` unconditionally at line 76.
- [`finish_project_navigation`, lines 84–102](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/projects.rs#L84-L102) rejects selection but cannot undo that catalog mutation.
- [`forget_chats`, `src/ui/chats/codex.rs:261–287`](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats/codex.rs#L261-L287) advances `session_catalog_epoch`, removes the row and pending opening, and removes its workspace.
- Normal `refresh_sessions` checks the captured epoch before applying its result (`src/ui/chats.rs:564–576`), and normal Codex catalog paging does likewise (`src/ui/chats/codex.rs:60–63`). Project discovery bypasses the existing invariant. `Workspace::session_catalog_epoch` explicitly documents that pre-delete catalogs must not resurrect rows.
- Core deletion reaches other windows through `WindowGroup::forget_elsewhere`; Codex native deletion events are consumed once and forwarded to all group windows by `watch_codex` (`src/ui/workspace/windows.rs`).

The tests exercise **both drivers**, including production `open_project`, its full result closures, `set_sessions`, `forget_chats`, `finish_project_navigation` and the navigation invalidation method. They verify that the generation guard rejects navigation while the stale row is nevertheless restored. They do not test a server's ability to delete a session or a real network scheduler: transport is an explicitly held typed completion.

### Repair direction

All catalog-producing paths should capture and validate the catalog epoch, not just normal refresh/paging. Re-read current metadata if a still-current project navigation needs a result; do not silently abandon the user's current project selection merely because an unrelated deletion changed the epoch. Review the similarly unguarded catalog-returning `start_chat` and `new_session` callbacks (`projects.rs:188–207`, `chats.rs:336–353`) as the same class, **not separately reproduced findings**. No production-ready catalog patch is claimed here.

## PN-2. Single-clicking another chat area steals keyboard focus from the session list [P3]

### Two routes to the same defect

- **Already loaded root:** Leave root A's retained area with `files:README.md` selected, switch to root B, then single-click A in the sessions list. The click first focuses the list. `select_session(..., clicks=1)` explicitly passes `focus: false`. Nevertheless, the switched-root branch calls `focus_active` unconditionally and hands the keyboard to A's retained file document. Single-clicking the current area does not do this.
- **Unloaded root:** Single-click a root that has to resume. The same switched-root branch passes `None` to `resume_key`. When the resume completes, `finish_chat_resume` treats `None` as permission to focus (`open.is_none_or(...)`). Merely guarding the immediate `focus_active` call therefore leaves a delayed focus steal.

This affects continued keyboard navigation or F2 in the session list after a single click. It does not require a slow network for the loaded route. Selection of the retained file/pane itself is intentional and is not classified as a defect; the bug is ignoring the caller's **keyboard-focus intent**.

### Source

- The real row-click listener focuses `session_list.focus`, then calls `select_session` (`src/ui/panels/session_row.rs:211–218`).
- `select_session` documents one-click preview vs double-click keep/focus and sets `focus: keep` (`src/ui/chats.rs:291–307`).
- [`open_chat` switched-root branch](https://github.com/Proteus-harness/Proteus-desktop/blob/75bf201764278eac4b50d156650edcf1429101ff/src/ui/chats.rs#L119-L137) calls `resume_key(key, None, ...)` at 134 and `focus_active(...)` at 136.
- `finish_chat_resume` passes `open.is_none_or(|open| open.focus)` into production `pending::may_focus` (`src/ui/chats.rs:267–287`).
- `focus_active` resolves the selected tab and `focus_tab` directly invokes a Chat or document FocusHandle (`src/ui/tabs/mod.rs:375–392`). List Up/Down/F2 actions are scoped to the list's focus context (`src/ui/panels/session_list.rs`).

`candidate-focus.patch` is **not applied to production**. It conditions the immediate call on `open.focus` and propagates `Some(open)` to the resume. On the extracted-method harness, both regressions become green and both existing same-area/double-click controls remain green. It still needs genuine Workspace/GPUI regression coverage and native interaction before publication.

## Evidence and limitations

- `make_probe.py` extracts whole relevant functions from the pinned source. `extraction.json` records their source ranges and body SHA256. Changes are visibility normalization plus the helper return type path; no production control flow is reimplemented inside those extracted methods.
- The real unchanged `proteus-tabs` crate supplies `ChatSpaces`, `TabLayout`, IDs, and their transitions.
- GPUI Context/Window/focus calls, unrelated Workspace integration, typed catalog DTOs and blocking transports have small stand-ins. A queued closure models “result read before deletion, UI completion after deletion.” The `select_chat_space` integration is a narrow stub using actual `ChatSpaces`; fully loaded and unloaded focus routes are checked separately.
- **Observations/controls: 6 passed**, 4 desired-invariant tests intentionally ignored in that run (`observations.log`).
- **Desired-invariant run: all 4 failed**, exit 101 (`regressions.log`): Core ghost row, Codex ghost row, immediate single-click focus, delayed single-click focus.
- **Candidate focus only: 2 regressions + 2 controls passed**, private target directory (`focus-fixed.log`). Catalog regressions are not claimed fixed.
- Native GUI event delivery, actual keyboard behavior, true HTTP/Codex transport races, full Desktop suite, portable build and full codebase coverage were **not run**.

## Reproduce

From this Desktop checkout, with the prepared Rust toolchain:

```sh
python3 audit-project-lifecycle/make_probe.py
CARGO_TARGET_DIR="$PWD/audit-project-lifecycle/target" cargo test --offline --manifest-path audit-project-lifecycle/probe/Cargo.toml
# Expected exit 101, all four desired invariants fail on this HEAD:
CARGO_TARGET_DIR="$PWD/audit-project-lifecycle/target" cargo test --offline --manifest-path audit-project-lifecycle/probe/Cargo.toml -- --ignored
# Test-only candidate already generated in focus-fixed/:
CARGO_TARGET_DIR="$PWD/audit-project-lifecycle/fixed-target" cargo test --offline --manifest-path audit-project-lifecycle/focus-fixed/Cargo.toml regression_ -- --ignored --skip deleted
CARGO_TARGET_DIR="$PWD/audit-project-lifecycle/fixed-target" cargo test --offline --manifest-path audit-project-lifecycle/focus-fixed/Cargo.toml control_
```

No production mutation or external effect is part of any probe.
