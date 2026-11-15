# Workflow source assembly: PR86 Modules + PR106/107/109/153

## Result and limits

**Source-only composition candidate, NOT COMPILED / NOT RUN. No new finding or new production behavior was authored in this pass.**

This addresses the specific unresolved composition task named in [PR155's integration plan](https://github.com/Qweasd123tg/proteus-modules-dot/blob/2f8e4011b9cc9a959263afd986930bc62800d0a1/docs/integration-plan-2026-11-15.md): retain the old Modules history-normalization **and** compactor correction while composing the later workflow simplifications.

The five exact published patches apply in both specified orders on current Modules source. Their 17 target files are byte-identical. No conflict was forced, no functional hunk dropped, no manual source correction made, and no dependency pin changed. Independent source review found no blocker at the inspected joins.

This narrows a source-composition gap. It is **not full integration, compile qualification, a complete repository audit, runtime success or deployment readiness**.

## Identity and selection

Fresh refs:
- Modules main/base: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Delivery read revision: `2f8e4011b9cc9a959263afd986930bc62800d0a1`.

Current Modules Cargo dependencies remain pinned to **`41bdfffa6e70228278b4abc758b7f81a12672f35`**. The obsolete pin in the original #86 README is not restored. Both copied Cargo files are unchanged. Current Core main is not silently substituted for the pinned contracts.

Inputs, exact hashes and remote paths are recorded in `COMPOSITION.json` and `SOURCES.json`:
1. #86 **Modules** `modules-history-compaction.patch`, including both coupled changes. The unrelated Core config patch is not included.
2. #106 `sampling-lifecycle.patch`.
3. #107 `workflow-json-codec.patch`.
4. #109 `runtime-instruction-propagation.patch`.
5. #153 `private-phase-projection.patch`.

`composed-workflow.patch` is an **alternative representation of those five patches**, against the exact current Modules base. Do not apply it on top of the same five changes. Partial or different upstream trees need their own final-diff reconciliation, not forced hunks.

Patch SHA-256: `9a479476afc511eafb840f92058475be62dfb92a9ff7d7e195ffd39d79bc95b7`.

## Preserved joins reviewed in source

| Boundary | Preserved responsibility |
|---|---|
| #86 history normalization | The shared helper changes only model history, closing unresolved historical calls with request-scoped synthetic outputs. Durable history stays separate. Existing real results and the existing Codex call-site order are retained. |
| #86 compactor | Every message remains in summary input. Request-scoped tool-call/result containers are not reinserted as independent context after their calls are removed. Ordinary non-tool Request context retains the previous path. The paired fix is not omitted. |
| #106 sampling | All five callers keep phase selection and persistence decisions. The helper preserves preparation → compaction/ACK → adopted messages → optional tool suppression → request/model/response/validation ordering. |
| #109 instructions | The shared builder adds supplied runtime blocks once between base and phase blocks. #106 still calls that builder. Codex retains its existing instruction-block path rather than receiving a second copy. |
| #153 private phase identity | Only newly appended terminal plan/draft suffixes become fresh private projections. Tool-bearing and final responses retain canonical identities and caller-owned persistence. |
| #107 JSON boundary | Four explicit workflow dispatches remain; input/output codec duplication is centralized and WorkflowFailure propagates through the existing result path. |

The five #106 sampling callers are single-loop ordinary round, single-loop forced final, plan, execute and review. Tool suppression remains enabled for forced final/review and the final forced-text plan round, not all rounds.

The common history distinction is retained: Request scope does not by itself make a tool result independent context. Conversely, #153's nonempty terminal phase projections are not converted into durable history merely to accommodate normalization or compaction. The existing scaffold adoption/classification code is not weakened.

Review was limited to functional request-history, sampling and compactor composition. Cancellation/process mechanisms, security and excluded Git/worktree behavior were not investigated or exercised.

## Checks actually performed

- Verified **28 Git blobs**: 21 copied current Modules source/context files and seven exact published inputs/documentation artifacts.
- Applied these two orders with system patch and **zero fuzz**:
  - #86 Modules → #106 → #107 → #109 → #153.
  - #153 → #109 → #107 → #106 → #86 Modules.
- Some hunks needed line-number offsets; all applied successfully without manual resolution.
- Compared all **17 target files**, not only a summary diff. They match byte-for-byte.
- Generated the combined patch from the baseline and composed result.
- Applied that combined patch to another owned baseline copy; all 17 target files match the recorded target hashes.
- Reverse application restored all 21 copied baseline files and removed the five newly introduced target files.

The forward/reverse directories also contain different patch backup `.orig` files. **Whole-directory equality is not claimed.** These are copied source subsets, not complete buildable repository checkouts. The target manifest's hash is not a Git tree ID or built-binary identity.

Actual logs: `text-composition.log`, `text-combined-apply.log`. Final target identities: `COMPOSED-TARGETS.json`. No test execution is encoded by those files.

## What test evidence does and does not carry over

The composed source includes 13 test functions introduced by the selected proposals:
- #86: six workflow-history tests and one compactor test.
- #109: three instruction tests.
- #153: three private-projection tests.

These are a source inventory, **not 13 executed passes or a new test suite**. No additional test was invented merely to increase the count.

#86's historical 121 scoped results belong to its older base, dependencies and binaries. They were not rerun and do not qualify this composition. #106/#107/#109/#153 source and text reviews likewise do not become runtime results through combination.

Important remaining gaps:
- No combined actual ACK/compaction/steering run.
- #153's new FakeHost tests use default acknowledgements without canonical revision; they do not establish real ACK replacement. #86 includes a separate synthetic ACK test, but the two together are not an executed cross-feature regression.
- Empty-part private messages remain outside the existing nonempty-parts ephemeral classification.
- No new accounting, completion-delivery, provider-terminal or media guarantee is established.
- An arbitrary compactor violating its contract is not repaired by this composition.
- No full crate/workspace check, formatter, process boundary, GUI, real provider or benchmark was run.

Python 3.12.14 and system patch performed only text/hash operations. Cargo, rustc and rustfmt are unavailable.

## Next useful qualification, once toolchain is available

1. Materialize the exact Modules base in a clean complete checkout and choose either this combined patch or the five inputs, not both.
2. Inspect the final diff and confirm the unchanged current dependency pin.
3. Run the project's scoped workflow and compactor targets on that exact composition. Then bind all results to final source, dependency and binary identities.
4. Exercise benign synthetic unresolved-history input with and without actual compaction, preserving real results and excluding synthetic outputs from durable history.
5. Exercise private plan/draft identities, canonical ACK adoption and steering reanchor together, including no-steering and intervening-tool controls. Check normal and resumed history projections.
6. Cover all five sampling callers and runtime instruction blocks, including forced-tool-disabled paths.
7. Only after the required checks pass should an upstream integration or deployment change be considered.

No promise of future automatic execution is made. Publication of this source assembly in the delivery repository is not upstream integration.

