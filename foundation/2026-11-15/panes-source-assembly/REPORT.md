# Active-pane navigation: coordinated source-only Desktop/Extensions proposal

2026-11-15 UTC. **Source composition accepted conditionally; release/rollout HOLD.**
This is not a compiled integration, a native UI reproduction, or a production fix.
No application, provider, extension binary, HTTP fixture, wire test, packaging,
installation or benchmark was run. Upstream and user data are unchanged.

## Exact revisions and alternatives

- Desktop: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Extensions: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
- Delivery snapshot: `fca5326f1dc52b1524f89f26506fdb07f014d74d`.
- Desktop Cargo's Core contracts pin stays
  `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Desktop `repositories.json` pins the same **unpatched** Extensions revision
  `f82b3ad753cf397f8a931b193aa1943af1ef07a7` inspected here. Neither that pin nor
  any dependency manifest is changed.

32 files were verified by exact Git-blob hash against fresh pinned trees:
28 baseline/reference files and four published patch/plan files. Whole files
support provenance, not an audit of unrelated contents. The copied trees are
incomplete source subsets, not buildable checkouts.

Selected published sequence:

1. #146 `navigation-bootstrap/navigation-bootstrap.patch`, Git blob
   `94d275e5305fb08a7e08844c2e42bbf567bad25e`, on Desktop.
2. #150 `active-pane-documents/desktop-active-pane-documents.patch`, blob
   `b16f10f91a7785647ba632d4aaac1dbb6dd3f91e`, **after #146**.
3. #150 `active-pane-documents/extensions-active-pane-documents.patch`, blob
   `c3e970ea12138a9e466713d4630d399b8a7b3918`, on Extensions directly.

Paths above are under `foundation/2026-11-15/` in the delivery snapshot.
The published #155 integration plan is reference only.

The supplied `desktop-coordinated.patch` is an **alternative to #146 plus the
Desktop half of #150**, applied to the exact unpatched Desktop base. Do not add
it on top of those originals. `extensions-coordinated.patch` is byte-identical
to #150's Extensions patch, not an extra change. Apply the pair to separate
repositories; do not concatenate their relative paths into one repository.

No source edits, policy choices or new abstraction were introduced during
assembly. All 12 resulting changed files are byte-identical to the already
reviewed #150 candidate trees. Other UI/settings/SDK candidates, including
#144, #148 and #149, are not part of this assessment.

## What source composition establishes

- #146 then #150 Desktop, and #150 Extensions, apply with `patch --fuzz=0`.
- #150 Desktop alone fails its dry-run on the pristine base at the bootstrap
  hunk. This is an expected prerequisite check, not a defect in the selected
  sequence; no manual conflict resolution was used.
- Both delivered per-repository patches apply to their exact base, reconstruct
  the same materialized source subsets, and reverse to all 28 baseline files,
  removing the two added test files. Patch-tool backup files are not target
  source and are excluded from byte comparisons.
- Combined change: Desktop 5 files, +126/−16; Extensions 7 files, +160/−10.
  These totals include documentation and proposed tests. They are not a
  performance or complexity-reduction measurement.

## Preserved common invariant and its limits

The coordinated contract is **per-context navigation metadata from one layout
sample**, with two distinct values: the existing focused `document`, and the
extension-owned document arguments of each active pane in the displayed chat
space. The list is not inferred from retained views, from focus, or from a
shared session cache.

### Producer and bootstrap

The #146 bootstrap hunk now calls #150's `document_navigation` helper. It
retains Context, optional session snapshot, then NavigationChanged ordering.
The initial metadata event is not suppressed merely because another context
already supplied the shared session snapshot. Existing announcement guards
are retained without further lifecycle modifications. An attempted send is
**not a transport ACK**, and no exactly-once render/delivery claim is made.

The three inspected Event producers in `runtime/scopes.rs` populate both
fields: bootstrap, workspace metadata refresh, and ordinary scope events.
The existing Event fixture receives its new member solely as constructor
maintenance. No adjacent process/authority behavior is analyzed or changed.

`DocumentNavigation` preserves the previous native lifetime/displayed-space
checks and focused-document meaning. Both projections read one TabLayout;
only documents owned by this extension are included. Inactive retained tabs
and other/background chat spaces are not selected by this projection.

**This is not actual visibility.** Settings replaces the rendered main area
without making this logical list empty. Additional active-pane previews can
remain eligible for reads under Settings. Occlusion/minimization is not
observed. This proposal does not suspend offscreen work or measure fewer
reads. Cold cache loads and existing invalidation can still read documents
outside the selected list.

### Consumer and Files

SDK stores the list per context; the current context owns it on Host and
inactive contexts on Scope. Switching moves the Vec using `mem::take`, not
a session-shared projection or a deep JSON clone. A fresh first context and
final-context retirement reset the new list. Existing focused-document
cleanup semantics are deliberately not repaired by this proposal.

Events replace the whole list. Absence means empty, never a singleton focused
fallback. A present malformed list returns a decode error before assigning
the new focused document/list. This is **not** an all-or-nothing message
transaction: earlier context routing can already have occurred.

Files changes only cached-age eligibility from focused equality to membership
in this list. Existing path/mode keys, session cache ownership, cold loads,
invalidation, checked timestamps and poll interval are unchanged. Shared
cached previews can reuse a refreshed snapshot; no universal one-read-per-
frame/window guarantee or scheduling-fairness improvement is established.

Costs remain explicit: one owned argument list per event and retained context,
serialization bytes and linear membership scans. More active panes can cause
more eligible reads, including under Settings. No hard cap, RSS/CPU/latency
measurement or performance win is added.

## Feature and pin compatibility

Protocol remains 4; `documents.active_panes.v1` is additive. Desktop includes
the list even when it is empty, and Files adds the feature to required_features
without removing its previous requirements. The unchanged manifest parser
checks every required string against Desktop's FEATURES list. This supports
the following **source-level**, not executed, compatibility assessment:

| Pair | Narrow source result |
| --- | --- |
| Baseline Desktop + new Files manifest | Required-feature validation rejects the missing feature, rather than claiming the new contract works. |
| New Desktop + new SDK/Files | Selected producer fields and typed consumer agree; compilation, delivery and native qualification remain outstanding. |
| New Desktop + baseline SDK/Files | Old event consumer reads focused document and ignores the extra JSON key; plural refresh is not obtained. This is not an all-packages qualification. |
| Baseline Desktop + new SDK, package not requiring the feature | Absent list decodes empty; focused field remains separate. A package using the new semantics must declare the feature. New Files does declare it. |

The local SDK dependency is `proteus-extension = { path = "sdk" }` in the
Extensions workspace; Files consumes that workspace dependency. No new crate
or Core DTO is needed by the inspected change. Keeping the existing contracts
pin is source-consistent for this local protocol addition, **not evidence that
the whole application builds with that pin**.

The default recorded Extensions source is still the unpatched revision.
Applying only Desktop cannot make the pinned Files use the new contract.
A future release must select and verify a real Extensions commit containing
the SDK and Files changes, coordinate the Desktop producer, and then update
the recorded release pin (or explicitly select both corresponding source
trees for an authorized qualification build). No such commit/pin/binary
pair is selected here; no SHA is invented. **Packaged integration and rollout
therefore stay HOLD.** Sources selection or binary reuse must not be mistaken
for confirmation that the new pair was built or delivered.

## Verification limits and handoff

Rust, Cargo and rustfmt are absent. Desktop requests Rust 1.95.0; no toolchain
was installed. All Rust controls are **NOT COMPILED / NOT RUN**:

- Four new TabLayout projection tests and five new SDK context/list tests.
- Existing workspace-update payload and Files cached file/diff tests adapted.
- One existing Event test literal updated, not a new behavior test.
- #146's extracted ten-test fixture still names the old native helper. It is
  **not adapted, included as combined coverage, or run**. Its three separately
  proposed SDK controls are likewise not part of these selected patch texts.

Only owned Python stdlib bookkeeping/text hashing, JSON parsing, AST parsing
of the edited wire fixture, and system patch dry-run/application/reversal ran.
The wire module was not imported or executed. Its one added feature string
does not demonstrate production of active_pane_documents. No Python semantic
model substitutes for Rust, and no historical runtime evidence is transferred.

Before any production conclusion: compile the selected producer and consumer,
adapt or replace the stale bootstrap fixture, exercise actual initial/new-
context metadata before render, shared-session context isolation, empty lists,
split/focus/close/rehost transitions, displayed-space gates and Settings,
qualify old/new feature admission, and inspect an intentionally built paired
artifact with its exact source pins. These are outstanding checks, not results.

Independent exact source review accepts the inspected junctions conditionally
and agrees with the release HOLD. It does not cover excluded security/process
areas, unrelated patches, or native timing. No new production merge is advised
on the strength of this package alone.
