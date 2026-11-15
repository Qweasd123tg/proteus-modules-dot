# Proteus: bounded integration plan for PR86–154

Date: 2026-11-15. **Documentation only. No candidate patch, project test, compiler, runtime or benchmark was executed in this planning pass. No upstream source or dependency pin was changed.**

## Scope and snapshot

This is a practical, limited map based on PR86–154 metadata, published README/REPORT material, selected dependency/composition evidence and live repository refs. It is **not a complete source inventory, review of every patch variant, combined-stack validation or release qualification**. Publication/merge in this delivery repository does not integrate the candidates upstream. Independent read-only review covered the early series and the resulting plan; its corrections are incorporated below.

Refs checked at the start and end of this pass:

| Repository | main commit |
|---|---|
| [Delivery](https://github.com/Qweasd123tg/proteus-modules-dot/commit/8d24a894a67c7d38e7b8461c45c3eeccb5ee246c) | `8d24a894a67c7d38e7b8461c45c3eeccb5ee246c`, through #154 |
| [Core](https://github.com/Proteus-harness/Proteus-core/commit/bcbda4435534a296c707a1daa250813d692f68e1) | `bcbda4435534a296c707a1daa250813d692f68e1` |
| [Modules](https://github.com/Proteus-harness/Proteus-modules/commit/c035142558f0fca43e9772fc0e50ca293abf1531) | `c035142558f0fca43e9772fc0e50ca293abf1531` |
| [Desktop](https://github.com/Proteus-harness/Proteus-desktop/commit/7eaf70c67dabba8595d98029c875ffc3f59209ad) | `7eaf70c67dabba8595d98029c875ffc3f59209ad` |
| [Extensions](https://github.com/Proteus-harness/Proteus-desktop-extensions/commit/f82b3ad753cf397f8a931b193aa1943af1ef07a7) | `f82b3ad753cf397f8a931b193aa1943af1ef07a7` |

[Modules Cargo.toml](https://github.com/Proteus-harness/Proteus-modules/blob/c035142558f0fca43e9772fc0e50ca293abf1531/Cargo.toml) and [Desktop Cargo.toml](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/Cargo.toml) still pin Core dependencies/contracts to `41bdfffa6e70228278b4abc758b7f81a12672f35`. Desktop's [repositories.json](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/repositories.json) selects the current component refs above. These are different pinning layers. Different SHAs alone do not prove wire incompatibility, but a new Core helper does not reach pinned consumers automatically.

## Recommended order, not an apply-all queue

**First: small, bounded simplifications.** Requalify [#86](https://github.com/Qweasd123tg/proteus-modules-dot/pull/86) Core config validation separately, and retain the Modules history-normalization plus compaction correction as one inseparable patch. Then prefer [#107](https://github.com/Qweasd123tg/proteus-modules-dot/pull/107) JSON codec (−30 lines), [#106](https://github.com/Qweasd123tg/proteus-modules-dot/pull/106) sampling lifecycle (−44), [#137](https://github.com/Qweasd123tg/proteus-modules-dot/pull/137) provider-source ownership (−18), and [#120](https://github.com/Qweasd123tg/proteus-modules-dot/pull/120) atomic completion drain (−8).

That order is a recommendation based on boundedness, not a dependency chain. Counts have different affected-source scopes and must not be summed as a product-wide saving. No speed/RAM improvement is established. #120 does not fix #118 delivery; its proposed competing-waiter control may also pass on baseline.

**Next: qualify coherent themes separately.**

| Theme | Candidates | Acceptance boundary |
|---|---|---|
| Workflow | #106/#107/#109/#153 | Five sampling callers, instructions, ACK adoption, private identities, actual compaction/steering |
| Core lifecycle | #87 → #88 → #89 | Cancel/settle, pending-input identity, descendant origins, cold history |
| Provider/terminal | #108/#110/#112/#113/#117; Core #111/#114 | SSE start/delta/error/EOF, typed failures, context recovery, media; deliberate consumer pins |
| File/text | #115/#116/#119/#124; #121 separately | Shell UTF-8 vs strict file EOF/budget, CRLF range/edit, actual Rust/bundled SQLite |
| Config/MCP | #86 Core/#137/#138/#139; Desktop #134/#135/#136 | Source ownership, cold load after Save, discovery staging, delayed Reload/Save |
| Desktop/Extensions | #144–#152/#154 | Separate project, pane, runtime, file-listing, image and rendering owners; native/wire checks |
| Measurement/build tools | #126–#130/#133/#141–#143 | Exact Python composition first, then real integration only where needed |

The old #86 Modules patch and the entire later workflow series have not been qualified together. Reconcile their final diff rather than dropping an earlier functional correction to make a refactor apply.

## Hard dependencies and variant selection

- **#87 → #88 → #89.** Standalone #89 applicability is not claimed.
- **#126 → #127 → #128**, using exact published patch bytes on the pinned Core base.
- **#146 → Desktop part of #150.** Extensions part targets its own base; new Files requires `documents.active_panes.v1`. This is a coordinated feature, not an older-host compatibility guarantee.
- **#119 → #124's `range-eol-on-PR119.patch`**, if #119 is selected. Otherwise use standalone #124. Original #119 and standalone #124 conflict; never apply both alternatives.
- Provider stack without #108: standalone #110 → #117's `context-stop-recovery-on-PR110.patch`.
- Provider stack with #108: #108 → #110's `anthropic-failure-on-PR108.patch` → #117's `context-stop-recovery-on-PR108-PR110.patch`. Original #108/#110 conflict. Select one variant per proposal.

See [#117 variants](https://github.com/Qweasd123tg/proteus-modules-dot/pull/117), [#124 variants](https://github.com/Qweasd123tg/proteus-modules-dot/pull/124), and [#150](https://github.com/Qweasd123tg/proteus-modules-dot/pull/150). #111 changes the generic Core completion helper; consumer pin updates are needed to obtain that code, not because different baseline SHAs alone prove incompatibility. #111 with #108/#110 has no declared combined qualification.

### Published text composition is not runtime integration

- #106/#107/#109: all six orders; #153 with that trio: two specified orders, nine identical target files, not every permutation.
- #86 Core/#137/#138: all six orders; #139 before/after the fixed three-patch sequence, not all 24 permutations.
- #134/#135/#136: the specifically published orders.
- #145/#152: both orders.
- #116: three positions around #119 plus rebased #124.
- #141: before/after the fixed #126→#127→#128 chain.

These are reported mechanical checks, not checks rerun here. They do not certify a giant combined tree. [#138 report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/8d24a894a67c7d38e7b8461c45c3eeccb5ee246c/foundation/2026-11-15/instruction-source-bootstrap/REPORT.md) and [#153 report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/8d24a894a67c7d38e7b8461c45c3eeccb5ee246c/foundation/2026-11-15/workflow-private-projection/REPORT.md) describe the exact limits.

## Evidence lanes: never combine their pass counts

### Historical Rust/runtime, not current-head GREEN

| Package | Published historical scope |
|---|---|
| #86 Core | 48 scoped tests; Save rejection RED/GREEN |
| #86 Modules | 121 scoped tests; process/local-HTTP and compactor scenarios |
| #87 | 35 scoped tests; four native cancellation cases |
| #88 | 16 user-input plus repeated 35 process tests |
| #89 | 63 scoped tests; model-free root→parent→leaf and cold history |

Those runs belong to older Core `89997df9`, Modules `3270dc0f` and their specific patched commits. Scopes overlap. Do not sum them into unique coverage or transfer them to a rebased tree.

[#103](https://github.com/Qweasd123tg/proteus-modules-dot/blob/71b6e452d4efaa07815754f1f94573323187e854/foundation/2026-11-14/upstream-revalidation/README.md) checked **78 exact-context hunks through in-memory text replacement**, not `git apply --check`, compilation or tests. It revalidates #86–89 only. Do not restore the obsolete Modules dependency pin `b5fac842…` from old instructions.

### Recorded Python synthetic results, not new runs

All entries below report Python **3.12.14** evidence from their packages. They are not new execution or independent raw-log revalidation by this planning pass.

| PR | Recorded outcome | What it does not establish |
|---|---|---|
| #126 | 6 candidate tests pass; no baseline RED | Full harness or historical table regeneration |
| #127 | 2 baseline failures; 9 new + 6 #126 pass | Native Pi/provider acceptance |
| #128 | 2 baseline failures; 7+9+6=22 candidate tests pass | 22 new independent tests or complete billing |
| #129 | 2 baseline failures; 7 new + 3 selected existing pass | Real measured workload |
| #130 | 2 baseline loader errors; 6 candidate controls pass | Full pytest/regrade |
| #133 | 22 expected outcomes; candidate 8 success + 10 expected rejects, baseline 2 success + 2 expected failures | 22 passing tests, real Ledger/full grader integration |
| #141 | Baseline 1 pass/3 failures; candidate 4 pass | Actual selected executable/digest was run |
| #142 | 1 baseline failure; 6 candidate tests pass | Real builders/portable release; builders were synthetic |
| #143 | 1 baseline failure; 5 candidate tests pass | Real packager delivery; subprocess/resolver mocked |

[#126 RUNTIME-SUPPLEMENT](https://github.com/Qweasd123tg/proteus-modules-dot/blob/8d24a894a67c7d38e7b8461c45c3eeccb5ee246c/foundation/2026-11-15/benchmark-usage-projection/RUNTIME-SUPPLEMENT.md) updates its historical source-only stage for exactly six tests. Initial NOT RUN text and later scoped evidence are different stages, not contradictory global statuses.

[#121](https://github.com/Qweasd123tg/proteus-modules-dot/pull/121) has 27/27 Python/SQLite expression expectations, **not execution of its Rust normalizer or bundled SQLite**. [#131](https://github.com/Qweasd123tg/proteus-modules-dot/pull/131) has seven proposed Node-side cases, zero executed passes; historical ESM linking failed before test bodies. Late Rust candidates remain **NOT COMPILED / NOT RUN**. Hashes, source review and text application belong in separate columns. Empty check-run/status lists are not CI PASS.

## HOLD and negative results are not a patch queue

| Work | Why it stays separate |
|---|---|
| #90 | Shutdown design; 28 scenarios not implemented/run |
| #91–#101 | Mostly docs-only source hypotheses on an older composed tree |
| #104/#105 | Research without production patches; #103 separately covers only #86–89 |
| #118 | Record-safe delivery/consumption contract unresolved; #120 does not close it |
| #123 | Close-only LSP leaves late unversioned diagnostics ambiguity |
| #125 | BeforeModel/model-deadline scope must be chosen first |
| #132 | Image identity/location contract blocks a simple resume path rewrite |
| #140 | Shared binding predicate would silently change hot/cold override policy |

[#94 ET-1](https://github.com/Qweasd123tg/proteus-modules-dot/pull/94) is a policy correction, not an established bug; the existing invalid-UTF-8 contract requires fail-fast. #92 durability is conditional on a power-crash promise not established by the report. #99→#111 and #102→#131 are finding/remediation pairs, not new independent incidents.

Additional limits worth preserving in integration:
- #117 is recovery-only, not accounting repair. #122 retains more root text and costs memory/copies.
- #131 and #113 repair different media boundaries. Neither alone establishes all-provider image support.
- #134 deliberately rejects legacy form syntax; #139 adds repeated schema compilation.
- #137 does not remove old materialized overrides; #138 does not recover absent assets.
- #153 leaves empty-part lifecycle and actual ACK/compaction qualification open.
- #150 describes logically active panes, not actual visibility; cached reads may continue under Settings/occlusion.
- #154 repairs one lookahead dependency, not EXT-L1 footnotes or universal warm/cold equivalence.

## Smallest useful integration workflow

1. Select one theme; record its base commits, exact patch hashes and actual consumer pins.
2. Review a clean final diff with the correct alternatives. Do not force conflicting hunks.
3. Run focused checks on that exact composition, then the affected real boundary: process, HTTP/SSE, native UI, renderer wire or packaging.
4. Bind results to final source/tree, dependencies and built-binary identity. Repeat affected checks after any code edit or conflict resolution.
5. Only then advance consumer/deployment pins and publish a small upstream integration change.

Old `result.json`, `pipeline_ok`, scores and binaries do not validate new code. #127 preserves a historical-success fast path; #129 does not rewrite old subject aggregates; #141 does not prove the executed digest. Historical regrading or a new benchmark must be an explicit separate task, not an implied consequence of merging a report.

