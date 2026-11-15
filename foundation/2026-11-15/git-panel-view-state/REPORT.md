# Git History ownership: per-view selection, shared data

2026-11-15. **Source-only candidate, not compiled or runtime-verified.** No
Rust tests, extension process, HTTP fixture, native window or real repository
operation was run. Only an isolated source copy and research files changed.

## Versions and deduplication

- Extensions main: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
- Desktop main: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Delivery main: `e9f689c5895927951be485fea5b53498c770a99c`, through PR146.
- Nineteen retained source/doc files match their pinned Git blobs exactly.
- This repairs the ownership mismatch in **existing PR85 git-view-state #1**.
  [The historical report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/e9f689c5895927951be485fea5b53498c770a99c/research/proteus-continuous-audit-2026-11-13/evidence/git-view-state/REPORT.md) contains older wire results,
  not a new run on these revisions. No new finding or severity is claimed.
- Git hash-identity #2 in that report remains outside this change. PR146
  navigation bootstrap is a separate Desktop source candidate; neither is
  claimed runtime-qualified or integrated here.
- Scope is panel UI state and lazy read caching only. No Git write-operation,
  filesystem action, process authority or security behavior was investigated
  or changed. Whole files are retained for source provenance, not an audit of
  every unrelated function they contain.

## The existing shared cause

Current `Git.tab` is one scalar for the Git instance. The SDK keeps one such
instance per live session, shared by that session's surfaces. It is therefore
not accurate to call the current scalar global across every process session.

Desktop `DeclarativeView.tabs` belongs to each view and tabs-node path. Selecting
History in view A changes A's native selection. A sibling's new-panel render
or `tab` action nevertheless changes the shared extension scalar. Then A's
`history_tab` may return a loading placeholder although A's native selection
still says History. Native tabs only send a tab action when selection changes,
so clicking an already-selected History is not a reliable repair path.

Current sources:

- `packages/git/src/main.rs:47,142-149,189`: scalar, new-view reset, action.
- `packages/git/src/panel.rs:336-354,403-410`: shared selector gates History.
- `sdk/src/host/instances.rs:1-3,18-23,35-64`: per-session instance ownership.
- Desktop `src/ui/extensions/declarative/layout.rs:83-95,145-161`: local
  selected tab and action only on a change; `view.rs` retains that map.

This is an owner mismatch, not a reason to eagerly fetch history for all
panels or duplicate the log cache for every view.

## Candidate

`git-panel-view-state.patch` changes two production files and their existing
test module:

1. Replace `tab: usize` with one `tabs: HashMap<String, usize>`, keyed by the
   existing stable opaque view ID. It replaces the scalar; it is not a second
   panel registry or a new SDK abstraction.
2. A new/unshown panel removes only its own selection entry. Missing entries
   keep the existing default, Changes/tab zero.
3. `tab` actions write only the addressed view using the exact previous
   `as_u64().unwrap_or(0) as usize` conversion. No new value-validation policy.
4. Thread the view through `panel` and `history_tab`. Only that view's value
   equal to one enables lazy History construction.
5. Remove the addressed entry in the existing `Extension::closed` callback.
   The current `session_changed` default reconstruction still resets all tab
   state as before. Its policy is not changed.

The production diff is **16 added / 8 removed lines**, net +8. Eight existing
direct panel test calls are updated for the view parameter; six new targeted
tests are proposed in the same test module. No new dependency, wire field,
framework, UI layout, label, keybinding or shared-cache copy is introduced.

## Lifecycle and performance boundaries

- SDK closes the addressed view before discarding its route/shown state
  (`host.rs:739-750,786-794`). The new callback removes the corresponding map
  entry; it does not clear shared history, working diff or commit caches.
- Same-session rehost preserves view identity and does not call `closed` in
  the inspected SDK path (`host.rs:619-637`). The native view entity keeps its
  own selection. This supports the source design; no actual detach/rehost or
  native event dispatch was run.
- Session changes retain the previous reset behavior. **This does not solve
  every possible mismatch between native selected tabs and extension state
  after session changes, process restarts or other resets.** Those are not
  silently redefined by this patch.
- `log`/`graph`/other caches remain session-shared and version-invalidated by
  the existing code. A Changes-only panel still does not request full History
  through `history_tab`, even if a sibling has already loaded it. Other panel
  metadata can independently query `/workspace/log`; lazy-read tests isolate
  that unrelated last-commit parent check.
- The map adds a string key and integer per recorded tab-action view until
  close/reset; normal dispatch ties those entries to live addressed views.
  No new hard entries/bytes cap is claimed. Removing entries need not shrink
  HashMap capacity. There is no measured RSS, CPU or latency improvement.
- Other preferences such as grouping, drafts, collapse state and commit
  selection remain shared as before. This is not per-view isolation of all
  Git state, and not a fix for the separate draft-lifetime or hash-alias issues.
- PR146 adds initial navigation metadata and may trigger existing session-local
  renders. It changes another repository/file. This patch keeps sibling tab
  identity during such renders but no cross-candidate runtime integration
  result is claimed.

## Six proposed focused tests: NOT COMPILED / NOT RUN

The new tests use the existing `Fake` fixture in `packages/git/src/tests.rs`,
the actual Git callbacks/builders, and synthetic data. The tab-related actions
are the only actions invoked by these additions. They do not invoke Git writes.

1. A remains populated History when fresh B and C panels render.
2. Addressed tab actions do not change a sibling; Changes stays lazy and two
   History panels reuse one loaded log.
3. Direct `closed` callback removes A's selection, preserves B and the shared
   log, and subsequent A panel construction defaults to Changes.
4. A synthetic stale selection for an unshown view is cleared locally without
   clearing another panel. This is a reset-rule control, not a new incident.
5. Direct `session_changed` callback retains the previous reset policy.
6. Non-History/invalid action values retain the previous inactive behavior for
   only the addressed view.

To distinguish lazy History loads from `last_commit` metadata probes, the new
fixture helper seeds `head_parent` and pins its refresh deadline. This is a
test fixture boundary, not a change to production polling or freshness.

The render helper invokes `Git::render` to exercise the new/unshown reset and
then calls the same production panel builder to inspect its returned tree.
It does not capture actual SDK wire output or execute native tabs. The close
and session-change tests invoke callbacks directly, not actual SDK lifecycle
routing. Native selection, event order, rehost and packaged behavior still
require real qualification. No baseline red or candidate green was observed.

## Actual checks

- Read relevant source/contracts and historical dedup evidence; independently
  review design, exact patch and proposed controls.
- Verify nineteen exact Git source blobs and their SHA-256 hashes.
- Apply the patch to an owned copy using `patch --batch --fuzz=0`; compare all
  three changed files byte-for-byte with the candidate.
- Forward and reverse `git apply --check --whitespace=error-all`: exit 0.
- Text diff/whitespace/caller inspection only. No project code executed by
  Python: stdlib was used solely for copying, source hashes and diff creation.
- Rust/Cargo are absent from PATH; no install, formatter, compilation, test,
  API call, process or native UI run. The historical 35-test count is not a
  result of this pass and is not reused as current qualification.

The next meaningful gate is the existing targeted extension-git suite followed
by the same-session two-panel wire/native scenario on the candidate. Until
then this remains a reviewed **uncompiled source proposal**, not production-ready.
