# Reconcile empty panes against their final siblings

## Status and scope

**Source-only candidate for known PR85 `desktop-layout` D5-2. NOT COMPILED / NOT RUN.** This is not a new finding, current runtime reproduction, or production-ready fix. No production checkout, preferences file, user document, installation or live application was changed.

Pinned Desktop: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
Extensions reference: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
Delivery/dedup baseline: `21229e413b9a6254e96f7d3ec9ad635179dade58`, including #148 as a source-only proposal with its separate weak-index cost.

The historical report and minimal fixture belong to [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) and are not duplicated in this delivery. Their executions used older revisions and an available Rust toolchain then. They are not tests of this candidate. No historical pass/failure count is imported as a current result.

## Common cause and consequential path

[`Node::normalized`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/crates/tabs/src/tree.rs) can retain an empty weighted pane to absorb room beside fixed, locked siblings. A later wrapper collapse and same-axis merge changes that pane's immediate siblings. The old retention decision is not revisited, although [`holds_room`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/crates/tabs/src/lock.rs) and [`TabLayout::validate`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/crates/tabs/src/layout.rs) judge its final siblings. A now-unnecessary empty pane can remain next to nonempty panes and invalidate the authoritative layout.

This is not merely a render-only gap. In current source, [`Workspace::update_tabs`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/ui/tabs/mod.rs) normalizes before applying the requested operation and persists the operation's result. The render path separately normalizes a clone. [`WindowGroup::persist`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/ui/workspace/windows.rs) preserves the saved layout, while [`preferences::save_at/load/parse`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/src/preferences.rs) serialize without first validating and reject invalid saved tabs on load. [`ChatSpaces::validate`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/crates/tabs/src/spaces.rs) validates each contained layout.

The earlier report demonstrated a preference reset with a retained backup if restart occurs before another layout operation repairs the saved state. Here only the current source chain was rechecked. There was no fresh save/load, restart or native-screen reproduction. This is not a claim of irreversible data loss or of a reset after every such close.

## Candidate invariant and implementation

At each split, automatic empty room-holders must be justified by **the final direct sibling set**, not by a parent they used to have.

The patch adds one `reconcile_empty` phase after the existing recursive normalization, share handover, flattening and local vacant-slot insertion, but before final child-count collapse/balance:

1. Explicit `keep` is a survivor even when empty or fixed. Nonempty panes and nested splits remain survivors with their existing objects and IDs.
2. If a surviving child is weighted, it can receive remaining room. No automatic empty child is needed.
3. Otherwise, if a surviving directly locked fixed pane needs room, keep only the first available weighted automatic empty pane in final reading order.
4. Mark all other direct automatic empty panes as removed before invoking the existing `size::hand_over`. Then collect surviving children in their original order and use the existing collapse/balance logic.

Surviving nested splits already reconcile their children recursively. A collapse exposes its node to the caller, whose flattening and final-sibling phase handle the new parent. The patch adds no whole-tree retry, fixed-point loop, parent pointers, new representation, dependency or protocol.

This is a shared normalization repair for operations using [`TabLayout::settle`](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/crates/tabs/src/ops.rs), not separate patches for close, move, extract, retain or lock. It does not weaken validation or add a save-time repair fallback.

Production delta: **37 added lines, no removed lines** in `tree.rs`. This is deliberately not a LOC-reduction claim. The benefit is a single final-sibling rule rather than caller-specific repair or repeated normalization.

## Preserved policies and limits

- The original pre-merge `size::hand_over` stays in place. Moving all handover after flattening would change how an outer removed share is distributed among descendants of its recipient.
- The added handover uses the existing rule: prefer a surviving weighted predecessor before a following sibling. This is not a globally nearest-by-distance rule. All removed candidates are marked first, so an about-to-be-removed holder cannot receive another's share.
- Removed fixed children do not donate weighted shares. Existing `size::merge`, final all-fixed `balance`, collapse and stale-lock forgetting remain authoritative. The proposal does **not** promise preservation of every locked pixel count in every topology or undersized window.
- Nonempty panes, tabs, pinned order and IDs are not rebuilt. Removing an obsolete empty holder can change focused pane through the existing pre-operation-order fallback; no new focus policy is introduced.
- Explicit keep and the existing fully-empty fallback are retained. The first automatic weighted holder is chosen only when final siblings require one; its selection is deterministic in reading order, not an extra UX preference.
- This pass assumes the existing model's valid/public-operation context. It does not harden malformed arbitrary trees or change deserialization/validation acceptance.

## Cost

The phase adds scans of immediate children. If none must be removed, it returns the original vector. Removal constructs temporary decision/survivor vectors and calls the existing handover helper; predecessor/follower searches can be quadratic in split width. It does not clone complete subtrees or repeatedly normalize the whole tree, but no latency, allocation-count, CPU or RSS improvement is claimed. No performance measurements were run.

#148's extra live-runtime index is independent and still has its documented cost. This candidate does not offset that cost or establish combined application performance.

## Eight proposed tests, all NOT COMPILED / NOT RUN

The new `crates/tabs/src/tests/normalization.rs` is included in the existing tabs unit-test target and uses the real model APIs/types and existing serde dependencies. No Python behavioral rewrite is substituted.

1. Historical public close sequence, mirrored across both axes/directions: final validity, survivor order, retained focused pane, fixed size and its axis geometry in the fitting fixture, plus round trip.
2. Several merged holders: only the first required holder survives; existing focus fallback, survivor IDs and fixed values remain.
3. Weighted survivors on both sides: predecessor-first share donation, tab order, pin count and active tab.
4. A nonempty nested weighted sibling can absorb room; it is not mistaken for an absent receiver.
5. Fixed outer merge: an inner holder converted to fixed pixels is removed without treating those pixels as a weighted donation.
6. Explicit empty keep, including fixed keep. This exercises internal `Node::normalize(Some(...))`, not the public placeholder-selection policy in every case.
7. A genuinely needed holder remains; after all tabs are removed, the existing weighted/focused empty choice survives.
8. Alternating-axis wrappers at depths 1, 3 and 9 collapse in one operation and leave a valid settled result.

Round-trip checks serialize/deserialize `TabLayout` in memory and validate it. Fixture idempotence checks apply one additional no-op retain to the repaired state. They are not universal floating-point/idempotence proofs. The tests do not exercise Desktop preference-file I/O, native geometry delivery, drag, restart, writer timing, or the preference fallback.

There is no current baseline-red/candidate-green observation. All existing tabs tests are also NOT RUN in this pass. Required before adoption: compile/run the tabs package tests, repeat the historical sequence and persistence fixture against the candidate, cover deeper/composed operation sequences, then exercise the relevant native workflow. The historical operation generator was not rerun.

## Dedup and composition

D5-2 was already reported in PR85. D5-1 delayed navigation is not fixed here. The candidate changes only the tabs normalization model and tests, not Desktop runtime registration, bootstrap announcements or Git state from #146/#147/#148. Their runtime composition and cumulative costs remain unqualified. No security/flagged directions were investigated.

## Actual verification

- 19 source/doc blobs are checked against pinned Desktop tree metadata; prior report/fixture identity is recorded separately.
- Independent design and exact-patch source review found no blockers. Patch SHA-256: `005d31aae8ae639913ffcaa9762226f8d76eb87b6edcc3a0717edb0ed3aaf1c9`.
- Strict patch application with zero fuzz, forward/reverse `git apply --check --whitespace=error-all`, and three byte-for-byte candidate/application comparisons succeeded in an isolated copy.
- Only source/text/hash/diff bookkeeping was executed. `cargo` and `rustc` are absent from PATH; no installation, Rust compilation, rustfmt, project test, native app, provider request or live filesystem experiment was performed.

The result is a reviewed source proposal, not proof that the application now preserves preferences after this workflow.
