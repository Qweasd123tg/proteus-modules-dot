# Active-pane document freshness: uncompiled cross-repository proposal

2026-11-15. **Source-only prototype, not a verified runtime fix.**

## Known family and chosen contract

This follows existing PR85 `document-refresh`, not a new discovery. Its historical report demonstrated that Files refreshes only the focused document while a different document can remain active in a neighboring pane. Those older Files/SDK/TabLayout experiments are not rerun here.

The existing protocol promises one active/focused document; it does not promise plural native visibility. This proposal explicitly adds a narrower reusable contract:

**For each context, publish the arguments of this extension's active tabs in all panes of the displayed chat space, separately from the focused document.**

The source already distinguishes these concepts: TabLayout::visible iterates each pane's active tab, while Host::active_document selects only layout.active(layout.focused). The new paired DocumentNavigation projection samples the same layout once for both. Files uses the list to decide whether an existing cached preview is due for its ordinary recheck.

### This is NOT actual visibility

The name is `active_pane_documents`, not visible documents. Settings replaces the native tab area but does not change its logical tab layout; this proposal deliberately leaves that lifecycle untouched. Multiple cached active-pane previews can remain eligible for reads **under Settings**, in addition to the formerly eligible focused preview. Occluded/minimized windows are not detected. No claim of offscreen suspension or lower I/O/CPU/RSS is made.

Inactive retained tabs and background chat spaces are excluded from the projection. That does not mean they can never cause reads: a missing cache entry still loads, and existing session_opened/run_settled invalidation can clear caches. This changes cached-age eligibility only.

## Pinned sources and stack

- Desktop: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Desktop Extensions: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
- Delivery at start: `d2095a9a6af34c4fc285d962c7fd1d2dbc6bed02`, through PR149.
- Twenty-one source/doc snapshots match exact Git blobs; SOURCE-BLOBS.tsv records identities.

**Desktop patch requires the PR146 navigation-bootstrap candidate first.** Its baseline is pinned Desktop plus that patch. The Extensions patch is against pinned Extensions directly. PR146 itself remains uncompiled: an initial NavigationChanged attempt is not a delivery ACK. Without that bootstrap, adding a field would still leave initial context projection unknown.

PR147–149 have different textual targets; no combined native/runtime qualification is claimed. In particular, new projection does not prove all rehost timing, registry delivery or normalized-layout combinations.

## Exact change

### Desktop

1. Advertise additive protocol-4 feature `documents.active_panes.v1`.
2. Add a whole-list `active_pane_documents: Vec<String>` to Event, serialized even when empty.
3. Replace the internal focused-only helper with DocumentNavigation: preserve old lifetime/displayed-space checks; filter both focused and per-pane arguments by extension; obtain both from one layout sample.
4. Populate the list on ordinary events, workspace metadata refresh and PR146's first-context bootstrap.
5. Update the existing Event fixture literal for the new field. This is constructor maintenance, not a new process-behavior investigation.

### Extensions

1. SDK exposes typed `Host.active_pane_documents` and stores it per Scope. Switching context transfers ownership with mem::take, not a list clone or a session-shared value.
2. Events replace the complete list. Owned JSON is taken before deserializing; no deep JSON clone is introduced. Absence yields an empty list. A present malformed list returns a decode error before replacing the two navigation fields.
3. Fresh first contexts and final context retirement clear only the new list. Existing focused-field cleanup/control flow is deliberately not refactored.
4. Files cached-preview eligibility changes from equality with focused document to membership in active-pane arguments. Existing path/mode cache, session ownership, checked timestamps, POLL interval, cold-load and invalidation behavior remain.
5. Files requires the new feature; the shared wire fixture advertises it. No filesystem operation, selection, focus, sidebar reveal or action behavior changes.

The two patches touch 12 files: **275 added / 26 removed lines including documentation and proposed tests**. This is semantic separation and shared metadata, not a LOC or measured performance reduction. There is no new renderer framework or dependency.

## Compatibility and costs

Protocol remains 4 because this is an additive advertised feature. Existing `event.document` keeps its focused meaning. New Files requires the feature so an old client is expected to reject its manifest rather than silently retaining old semantics. New SDK users not using the feature can receive events without the field; absence means empty, never a guessed singleton from focus.

New costs are one owned argument list per event and retained context, serialization bytes, and a linear membership scan in each cached Files render. The current context owns its list in Host; inactive contexts own theirs in Scope. Context switching moves those allocations. Replacing a list drops the old one; final-context retirement replaces it with an empty Vec. There is no new hard cap, global cache or native visibility tracker.

More active panes mean more eligible reads. Each existing path/mode cache can still serve sibling views in the same session, but this is not a guarantee of one read per window/frame or an I/O benchmark. No performance gain is claimed.

## Proposed tests: all NOT COMPILED / NOT RUN

- Four native-project pure TabLayout projection tests: two active document panes versus hidden tab; focus change and close; focused chat/other extension with owned sibling; empty layout.
- Five SDK controls with an inert renderer: projection before first render; independent lists for two contexts of one session; replacement/empty/absent semantics; SDK rehost and context close; new context starts empty.
- Adapt the existing Files file/diff loopback test: the checked document remains unfocused, is first removed from and then restored to the active-pane list; cached hidden interval remains lazy and sibling calls share the refreshed snapshot. The loopback test was only edited, never started.
- Adapt the existing workspace_update serialized-payload expectation. The process fixture change only supplies the new Event member.

These are not native Host/lifecycle tests. The real displayed-space/lifetime gates, initial/restart producer order, Settings behavior, native close/rehost and transport delivery still require qualification. The old PR146 extracted stub harness calls the previous native helper and must be updated before being reused. Adding a feature string to wire.py does not exercise this contract.

## Checks actually performed

Exact blob/hash verification, strict zero-fuzz patch application in owned copies, forward/reverse git apply whitespace checks, byte comparison against candidate files, and Python AST/JSON parsing of edited fixture/manifest text only. No project script or historical executable was run.

Rust, Cargo and rustfmt are absent from PATH. No build, Rust test, project wire test, HTTP fixture, native window, real user data, provider, install or benchmark was executed. The upstream repositories are unchanged. Whole source snapshots support provenance, not a claim that unrelated code was audited. Independent exact source review found no blocker for presenting the prototype with these limits.
