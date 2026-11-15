# Independent pre-patch normalization review

Verdict: final-sibling reconciliation is a justified narrow candidate for known D5-2, not a reason for a whole-tree retry loop. No runtime or Rust execution was performed. Exact implementation still needs review.

Current `normalized` recursively settles a child, then may collapse its wrapper and merge it into the parent. A formerly legitimate empty room-holder can thereby acquire different siblings. `holds_room` checks immediate final siblings, whereas the decision that retained this pane was made earlier. This is a structural ownership mismatch visible in the saved source, not fresh evidence of preference recovery at runtime.

The proposed placement after existing hand_over/flatten/local-vacated insertion and before final child-count collapse/balance is appropriate. At that point only direct empty Pane children need reconciliation: surviving nested splits already reconciled their own children; only collapse/flatten exposes nodes to a new sibling set. Preserve survivor order and existing Pane objects/IDs, do not rebuild nonempty panes.

Required precise predicate:
- Preserve explicit `keep` even when empty or fixed; do not replace the all-empty focused/weighted preference computed by `TabLayout::placeholder`.
- Treat every surviving nonempty child (including a nested split), and any explicitly kept empty child, as a survivor when deciding whether a weighted recipient already exists.
- Only if there is no such weighted survivor and there is a surviving fixed, directly locked Pane may one automatic weighted empty pane be kept. Choose the first in final reading order. All other automatic direct empties must be marked for removal before hand_over runs.
- Reuse `size::hand_over` on that complete final decision vector, then retain survivors and use existing final collapse/balance. Do not filter empties one at a time while choosing recipients: that can hand shares to another pane later removed and change the predecessor-first policy.

`hand_over` is predecessor-preferred, not globally closest by distance: it searches any previous surviving weighted sibling before considering following siblings. Preserve that exact existing rule. Fixed removed children do not donate weighted shares. A Fixed outer merge converts inner weights to fixed pixel lengths via `size::merge`; the cleanup must not reinterpret these as weights or invent a new weighted placeholder. If no weighted survivor is left, retain existing `balance` behavior, which intentionally converts all-fixed sizes to proportional weights. Thus an unconditional claim that every fixed/locked pixel value survives every topology is too strong; preservation must respect existing merge, collapse, lock-forgetting and all-fixed balance semantics.

Focused-pane settlement already uses the pre-operation pane order after normalization. Do not add a new focus heuristic. A removed automatic holder may legitimately transfer focus through that existing rule; explicit keep and fully empty layout fallback must remain intact.

Essential proposed controls: historical public close sequence; deeper alternating-axis collapse; several merged holders with first survivor selection; weighted nonempty siblings on both sides to check predecessor-first handover; nested nonempty weighted sibling; fixed-outer merge; genuine sole room-holder retained; explicit keep including fixed keep; wholly empty layouts and focused-ID preference; tab/preorder preservation, validate and serialization/load round trip; normalization idempotence after the repair. All are proposed, not run. Valid final state alone is insufficient if size shares, IDs, or focus policy changed.

No blanket double-normalize or repeated full-tree loop is justified. The extra phase can restore the final-sibling invariant in the existing recursive pass, without changing size policy or introducing a new normalization framework. Missing native/toolchain qualification is a delivery limitation, not evidence that this local design is impossible.

## Exact candidate review

Patch SHA256 independently read: `005d31aae8ae639913ffcaa9762226f8d76eb87b6edcc3a0717edb0ed3aaf1c9`.

No blocking source defect found. `reconcile_empty` implements the previously described final-sibling predicate: explicit keep is excluded from automatic empties; every other survivor, including a nested split, participates in weighted detection; a retained directly locked fixed pane permits the first automatic weighted holder only when no weighted survivor already exists. All removals are decided before calling the existing predecessor-preferred hand_over. A fixed empty exposed by merge is removed without donating a weight. Survivor order/Pane objects are moved, not reconstructed. The existing child-count collapse, balance, outer recursive processing, and focus settlement remain in charge afterward. This is one local sibling pass, not an additional whole-tree normalization.

The no-removal path returns the original vector. The removal path allocates an entries vector and a survivor vector and performs the existing hand_over search; no speed, allocation reduction, or whole-normalizer linear-complexity claim is warranted. Existing hand_over can search many siblings. Invalid preexisting trees with empty splits/duplicate IDs are not newly supported by this change.

The proposed test module path, crate-private access and sibling `assert_close` visibility are plausible: tests/tree.rs exposes that helper as pub(super). Temporary formatted strings in the deep fixture are consumed/copied into owned tab strings within the leaf call. The donor fixture's expected weights follow the existing rule: previous weight 2 receives the holder's weight 1, matching following weight 3, hence balanced weights 1 and 1. The multiple-holder case retains the first holder and focus falls to the preceding surviving pane via existing settle. Fixed-outer, nested-survivor and explicit fixed-keep controls distinguish cases that a simple empty-pane filter would mishandle.

Eight proposed tests include four directional public sequences, plus internal structural controls. The round-trip checks serde DTO equality and validation, not Desktop preferences persistence/recovery. Their second settle checks idempotence for these fixtures only; it is not a universal floating-point equality guarantee. Geometry checks target the surviving locked dimension, not all pane coordinates or all topology changes. No native focus or saved application preferences was exercised.

Verdict: coherent bounded source proposal, with no requested production correction at this stage. All eight new tests and existing tests remain NOT COMPILED / NOT RUN. No baseline-red/candidate-green observation, simulation, project execution, or new finding is asserted.

## Final prose review

Accepted the following locally read/hash-checked revisions:
- REPORT.md: `4682dfe5eaaa1a36e31506e522c871bb12bd36a707e9a4b13a5a997b1e45a6d7`
- README.md: `b8d441150d0861f11f5a759ba09e993519f528d855aa85437989077d679d844d`
- CHECKS.md: `931965034d44f73844ae3cba204109ee61bb7cb151ac9606d9a061d35f3df95f`
- Patch remains `005d31aae8ae639913ffcaa9762226f8d76eb87b6edcc3a0717edb0ed3aaf1c9`.

No blocking prose overclaim found. The report separates historical preference-reset observations from the coordinator's fresh persistence-chain source check, and does not claim current file I/O/restart recovery. It preserves both pre-merge and final-sibling handover policies, qualifies geometry and floating-point fixture idempotence, and explicitly states vector/scanning costs and potential quadratic handover searches. The +37 production lines are not advertised as a size/performance reduction. Eight proposed tests and all existing tests remain NOT COMPILED / NOT RUN. Source/blob/application checks are artifact evidence, not behavioral qualification; this closing review performed prose/hash inspection only. Known D5-1 and cross-candidate runtime composition remain outside the claim.
