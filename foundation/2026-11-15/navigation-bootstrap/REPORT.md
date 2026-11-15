# Extension navigation bootstrap: source-only candidate

2026-11-15. **Uncompiled proposal, not a verified runtime fix.** No Rust, SDK,
Files binary, HTTP endpoint, native window or provider was executed. Only owned
source copies and research artifacts were changed; upstream is untouched.

## Scope and provenance

- Desktop main: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Extensions main: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
- Delivery main: `785a83e6ca108932998b82b2bd51278e90e4fd62`, through PR145.
- Fifteen retained source/doc files match the pinned Git blobs exactly.
- This addresses **existing PR85 files-initialization #1**, not a new finding.
  Its [historical PR85 report](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) contains older wire
  experiments. Those experiments were not rerun on the current revisions.
- The functional scope is initialization of context navigation metadata.
  No process-authority, security, launch-policy, terminal or file-operation
  behavior is investigated or changed. Whole source files were retained privately for
  provenance and are excluded from this publication; not all their contents were audited.

## Common cause and narrow repair

Desktop startup sends Hello, announces every retained scope, and then renders
the attached views (`runtime.rs:260-295`). The announcement currently sends
Context plus an optional session snapshot (`runtime/scopes.rs:202-235`).
Neither of those carries the focused document. SDK stores `active_document`
from events, not from a document render (`sdk/src/host.rs:748-762`). The field
belongs to each context (`sdk/src/host/scopes.rs:7-12,67-86`).

Files intentionally rechecks a cached document only when its argument equals
that active document. A retained rendered document is not necessarily active.
The historical startup/restart sequence therefore left the visible active
document on the hidden-document cache policy until another navigation event.

The proposed invariant is small: **when a scope is first announced to an
available process, publish its current navigation metadata before its ensuing
view render**, independently of whether the session snapshot is already known.
Use the existing protocol event and Host selection method, rather than adding
another source of active state or treating all retained documents as visible.

### Exact production change

`navigation-bootstrap.patch` changes only Desktop
`src/ui/extensions/declarative/runtime/scopes.rs`: **12 added, 1 removed line**.

1. Capture `initialize_navigation = !scope.announced` before announcement.
2. Keep Context and optional snapshot delivery in the existing order.
3. For an initial session-lifetime announcement, send existing
   `NavigationChanged` using the same sampled session and
   `host.active_document(cx)`.
4. Set `scope.announced = self.process.is_some()` instead of unconditional true.

Step 4 is necessary for this guard: `scope_event(SessionOpened)` may schedule a
deferred start and call `announce_scope` while no process exists. `send` then
does nothing. Such an attempt must not suppress the later actual bootstrap.
Existing session/workspace bookkeeping stays unchanged. Restart already calls
`reset_scopes`, so the next announcement reseeds current navigation.

No helper framework, public field, protocol version, package-ID branch,
dependency or per-view navigation cache is introduced. The improvement is a
shared bootstrap invariant, not a reduction in source line count or a measured
performance improvement.

## Contract and behavior boundaries

- `NavigationChanged` is already used by `workspace_update` for metadata
  refresh. It is not limited to an exact physical click count. This patch
  reuses that mechanism; it does not invent a new event or SDK interpretation.
- The native `Host::active_document` still checks the displayed space, focused
  pane and owning extension (`host.rs:453-465`). No new plural-visible policy is
  selected. An absent document stays absent, not guessed from a retained view.
- Each new context gets navigation even when another context shares its
  session and suppresses a duplicate session snapshot. Session identity is not
  a substitute for context-local document identity.
- Ordinary already-announced SessionOpened does not get an additional
  bootstrap navigation. Its existing real event remains responsible for the
  current document. A genuinely unannounced scope followed immediately by a
  real event can still cause additional renders. No exactly-once-render claim.
- A newly attached/rehosted context can cause session-local existing views to
  render before its own view is registered. SDK restores each view's context
  before rendering. This is source reasoning plus proposed consumer controls,
  not a native rehost timing demonstration.
- `announced` means an announcement was attempted with an available process,
  **not a transport delivery ACK**. Existing send-error handling is unchanged.
- Existing non-session lifetimes get no bootstrap event. No lifetime or
  connection rules are changed.

## Explicitly not fixed

- PR85 files-initialization #2, document-only absolute Copy Path metadata.
- Split-pane visible-but-unfocused document refresh. This remains the same
  focused-document contract, not plural visibility.
- Poll fairness under traffic in another session; that separate HOLD remains.
- Lost live navigation on an already-announced context or all rehost/focus
  races. This repair is specifically initial/restarted/new-context bootstrap.
- Files listing knowledge PR145, history revision lifetime, and unrelated
  settings/catalog proposals. No closure claim is made for those families.

## Proposed controls, all NOT COMPILED / NOT RUN

`regression/generated/{baseline,candidate}.rs` contains the exact selected
production methods `announce_scope`, `reset_scopes` and `send`, wrapped in
small std-only fixture types. The ten tests cover:

1. Context → snapshot → navigation ordering.
2. Navigation when session snapshots are not requested.
3. No active document without guessing from retained views.
4. Deferred prelaunch announcement cannot suppress later initialization.
5. Reset and reseed from the current document.
6. Already-announced scope does not duplicate navigation.
7. Shared-session snapshot dedup still sends context-specific navigation.
8. Different sessions still receive their snapshots.
9. Non-session lifetimes remain context-only.
10. Missing context remains a no-op.

These fixtures do not execute GPUI, `launch`, the real restart/SessionOpened
caller, native Host filtering, transport or Files. No baseline failure or
candidate pass was observed. The reset test invokes the actual extracted
`reset_scopes`, not an actual restart.

`regression/sdk-navigation-tests.rs` proposes three additions to the existing
SDK host test module. They exercise the real consumer methods with a synthetic
renderer: first/hidden document metadata, independent contexts sharing a
session during a global render, and missing-document clearing without a
session lifecycle epoch. They have no API calls. They are **consumer controls**,
not baseline-red producer tests, and likewise were not compiled or run.

The existing Files active/hidden cache test and historical wire scenario are
relevant future integration checks. Even passing the proposed narrow controls
would not prove native startup/restart or packaged cross-repository behavior.

## What actually ran

- Remote revision checks and exact source Git-blob/SHA-256 verification.
- Independent source/design review before the patch and independent review of
  the precise patch and inert text generator.
- Python stdlib text extraction, **not project execution**, after that review.
  Generated methods retain the selected source text. Source/hash bookkeeping
  and patch application are not behavioral tests.
- Patch application to an owned copy with `--fuzz=0`, exact candidate comparison,
  and forward/reverse `git apply --check --whitespace=error-all` checks.
- Rust/Cargo were not present in PATH. No installation or substitute model run.

Independent review records and exact hashes accompany the package. This is a
reviewed source candidate for later compilation and native/integration
qualification, **not production-ready and not a confirmed runtime repair**.
