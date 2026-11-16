# Proteus: bounded integration plan for PR86–154

## Current integration decision, refreshed 2026-11-16

**Do not use the historical order below as an apply queue.** Upstream has already
adopted much of it. The original 2026-11-15 plan is retained below as historical
context; this section supersedes its refs, pending-work status and recommended
application order, not its historical evidence.

Fresh main refs were checked against the published patch targets:
- Core: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`.
- Modules: `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`.
- Desktop: `79499f2d639a3185384bed75f29b6919b811fe7c`.
- Extensions: `ae6479c5accc404d5a635fdeff1397a8b3016416`.
- Delivery before this documentation update: `f113e3848ba41870fa81e957c4f54bd3f94e3510`, through #167.

### Already adopted: do not reapply historical assemblies

| Delivery family | Current upstream evidence | Decision |
|---|---|---|
| #86 Core validation | Core [2192786](https://github.com/Proteus-harness/Proteus-core/commit/219278601251068b4f1d624d6ebce94922635c22); shared pass and original regression file retained at current main | Source scope adopted; do not reapply historical patch |
| #86 Modules recovery + compactor | Modules [d463a4b](https://github.com/Proteus-harness/Proteus-modules/commit/d463a4bfd931acd6ba044a984495b2e92d3e9f2a); all nine target files unchanged at current main | Both coupled changes adopted; not a new runtime pass |
| #145 Files listing knowledge | Extensions [ae6479c](https://github.com/Proteus-harness/Proteus-desktop-extensions/commit/ae6479c5accc404d5a635fdeff1397a8b3016416): failed listings remain unknown; failed collapsed reads expire on refresh | Adopted; do not reapply the source candidate |
| #147 Git per-view tabs | Same Extensions commit: addressed tab selection and close cleanup; history/cache remain shared | Adopted; not a native selection/reconciliation qualification |
| #152 folded Expand All | Same Extensions commit: known folded ancestors retain expansion/refresh intent without spending descendant traversal budget | Adopted; do not reapply or count as a new finding |
| #154 Markdown prefix boundary | Same Extensions commit: CR/LF lookahead revalidation for retained code/math prefixes | Adopted; EXT-L1 footnotes and universal warm/cold equivalence remain open |
| #156 workflow | Modules [d463a4b](https://github.com/Proteus-harness/Proteus-modules/commit/d463a4bfd931acd6ba044a984495b2e92d3e9f2a), with adapted tests | Review current code; do not replay whole assembly |
| #157 config | Core [2192786](https://github.com/Proteus-harness/Proteus-core/commit/219278601251068b4f1d624d6ebce94922635c22), followed by named models and inline roles | Old persistence diff is obsolete; inspect new source ownership |
| #158 provider | Modules [9a69146](https://github.com/Proteus-harness/Proteus-modules/commit/9a69146634cf1a5751a770fe0efe311fbcff68dc), including transport-test adaptations | Do not reapply old alternatives |
| #159 text and #163 list_dir | Modules [852efd3](https://github.com/Proteus-harness/Proteus-modules/commit/852efd31f54d90956814f1a6c4830a3c41c9eb92); #163 complete reverse-check succeeds | Already present, not pending fixes |
| #160 settings | Desktop [84923bc](https://github.com/Proteus-harness/Proteus-desktop/commit/84923bcd0c73843b1a04a2f47de658afa697beec), with adaptations | Review current behavior rather than reapply |
| #162 reporting | Core [55206ae](https://github.com/Proteus-harness/Proteus-core/commit/55206ae5e7d8d3fd8876e1dd345a577194f6d523); complete reverse-check succeeds | Do not replay or reinterpret historical scores |
| #164 portable compatibility | Desktop [48aa785](https://github.com/Proteus-harness/Proteus-desktop/commit/48aa78530460c54a5151106c8bdbb3faf3a399aa); both alternatives reverse-check | Apply neither alternative again |

These are source-adoption findings, not new runtime acceptance. Adapted tests,
formatting and later development mean an unsuccessful reverse-check alone does
not establish that a fix is missing.

### PR #86 source reconciliation, 2026-11-16

**Both #86 source changes are already adopted; do not reapply either historical
patch to current main.** This check is limited to #86 Core validation and the
coupled Modules history/compactor correction. It makes no new finding about
#87–89, other delivery families, or a combined runtime stack.

The published patches and checksum file were read at delivery
`f2264bbab27f0086f606e1caba43e5aadb44478b`. Their SHA-256 values match the
[original package](../foundation/2026-11-14/reviewed-simplification/SHA256SUMS):
Core `5e7be929ccb284ba5d1ebd4165e31d2245a54369c6983b723ed8a1c22621faf0`,
Modules `6d868451aacd1716d1d20c4c76ad46bb9b124d95dbaa7559897beca77a26d83f`.
Each patch passed `git apply --no-index --check --whitespace=error-all`
and was applied in an isolated copy of its exact preimages: Core
`89997df995df7c39b713e16aba216ecb19c8f497`, Modules
`3270dc0f894eaf4d0360306052b806099b8f5351`.
The output was compared with the adoption commits and the refreshed main refs
listed above. All 44 materialized source snapshots, both patch blobs, the
checksum file and the previous plan matched their Git blob identities.

- **Core:** at [2192786](https://github.com/Proteus-harness/Proteus-core/commit/219278601251068b4f1d624d6ebce94922635c22),
  four of seven complete target files equal the #86 output. The remaining
  differences are removal of an unused import, additional test registrations
  and fixture adaptations, and additional documentation; all #86 hunks are
  retained and the complete reverse-check succeeds at that commit.
  At current `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`, the
  [shared validator](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/crates/proteus-core/src/core/config/validation.rs)
  and [309-line regression file](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/crates/proteus-core/src/app_server/config_builder/tests/validation.rs)
  remain byte-identical to the patch output. Save and loader remain wired to
  `validate_semantics`; the separately read watcher still uses the loader and
  defensive rereads. Later named-model, inline-role and physical-path changes
  alter surrounding source, so current whole-patch reverse-check fails in four
  files. That failure is context drift, not evidence that #86 is absent.
- **Modules:** at [d463a4b](https://github.com/Proteus-harness/Proteus-modules/commit/d463a4bfd931acd6ba044a984495b2e92d3e9f2a),
  eight of nine complete target files equal the #86 output. The only difference
  in the ninth, `workflow/coding-workflow/src/tests.rs`, is two additional
  test-module registrations; `mod resumed_history;` remains present.
  All nine target files are unchanged at current
  `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`. This includes both the shared
  request-only missing-output normalizer and the compactor correction, not one
  half of that coupled change. Whole-patch reverse-check fails only at the
  changed test-registration context.

All **11 proposed test functions** remain in byte-identical new test files:
four Core validation tests, six workflow resumed-history tests and one compactor
test. Their assertions were read, including rejected Save state preservation,
request-only synthetic results, no repeated tool execution, interruption order,
canonical ACK and removal of request-scoped tool pairs from replacement context.
Independent read-only review repeated the patch/output comparison and found no
blocker to this source-adoption conclusion.

**No Cargo/Rust build, project test, process/HTTP scenario, native UI or benchmark
was run in this reconciliation.** Exact-current-head GitHub check-runs, commit
statuses and Actions runs were empty for both repositories, not PASS. The
historical 48/121 scoped passes remain historical. No upstream source,
dependency pin, deployed binary or active workflow was changed; later
model/source changes and combined runtime behavior still need their own gates.

### Extensions source reconciliation, 2026-11-16

A follow-up check used delivery `c9aa240cba9ec889429c0d821fba5ad67333cfe0`
and independently refreshed Extensions main, still
`ae6479c5accc404d5a635fdeff1397a8b3016416`. This is additional evidence for
#145/#147/#152/#154, not a rerun of the earlier #168 reconciliation.

The four published patch blobs were checked with
`git apply --no-index --check --whitespace=error-all`, then applied in an isolated copy
of their exact `f82b3ad753cf397f8a931b193aa1943af1ef07a7` preimages.
The resulting four production files (`files/src/tree.rs`, `git/src/main.rs`,
`git/src/panel.rs`, `markdown-render/src/render.rs`, all under `packages/`)
are byte-identical to the current upstream files. All 22 proposed Rust test
functions are present: 6+6 Files, 6 Git and 4 Markdown. Full comparison of the
three affected test files found only formatting/trailing-comma differences,
including the adapted existing Git call sites; no test assertions were dropped.
All 18 materialized preimage/current/patch/plan blobs matched their Git identities.

Upstream additionally contains two NDJSON warm/cold process controls in
[`tests/test_markdown_streaming.py`](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/ae6479c5accc404d5a635fdeff1397a8b3016416/tests/test_markdown_streaming.py)
and replaces the stale package-count literal in `tests/test_bundle.py` with
manifest-derived package identities/counts. Their source was read, not executed.
The commit author's Rust/Python pass totals remain author-reported: this check
ran no Rust/Cargo, Python project tests, packaged binary, wire or UI.
Exact-head GitHub check-runs, commit statuses and Actions runs were empty,
which is not PASS. Source adoption does not resolve last-good Files/error UI,
stale folded heads, broader native/session tab coherence or Markdown footnotes.

### Remaining bounded work and gates

1. **#165/#166 source cuts:** seven #165 cuts and three #166 Rust cleanups remain
   forward-applicable. All 20 target blobs match their published preimages.
   Qualify the four independent model-pack cuts together using the normal
   `python3 scripts/test.py -p model-pack --lib` gate: dead terminal reader,
   truthful OpenAI fallback-test scope, instruction prefix and metadata
   transport. Keep parser ownership, Core cache/mailbox and Desktop native
   changes separate because their behavioral boundaries differ. Text
   applicability does not establish native test success or performance gains.
2. **#167 inherited model choice:** a bounded source-only candidate now addresses
   choice-key persistence through plain file includes. It deliberately refuses
   inherited catalogue edits and clearing inherited selection. Its regression
   proposal has not been compiled or run; it is not a replacement for all
   config persistence or a runtime-qualified release.
3. **#161 active panes:** Desktop already adopted prerequisite #146 navigation
   bootstrap, but not `documents.active_panes.v1`. The old composed Desktop
   patch conflicts with the adopted bootstrap. Prepare only the still-missing
   Desktop delta, coordinate Extensions and native/wire tests, then explicitly
   update the component release pin. Do not ship Files requiring the capability
   before host support. Logical panes do not establish actual visibility.
4. **#166 skills sharing:** four duplicate implementations can have one owner
   without dropping the fifteen Python controls in either pinned lane.
   An isolated 50-file source-layout bundle was qualified with all fifteen
   shared Python controls in the current pinned lane and ten expected refusal cases. This is not the former
   bare-current-directory/private-entrypoint contract. Core remains pinned to
   `1fc3ef223d10322815dd9290a50d045bc95402bb` in that compatibility lane.
   Before active adoption, retain explicit packaging closure and obtain
   exact-head affected hosted CI. The source-bundle qualification does not
   supply toolchain, Git dependencies, binaries or outer resource envelope.
5. **#166 envelope:** requires an explicit new active frozen-source validation
   revision. Do not rewrite historical attestations or bypass freeze failures.
   NaN/insertion-driven history revision remains a separate semantic HOLD.

Desktop's current component manifest selects the Core/Modules/Extensions refs
above. Modules and Desktop compile-time Core dependencies instead use
`185225a7103088c444788374ca425d230060f55a`. These are distinct pinning layers:
do not roll them back to the historical `41bdfffa` below or blindly bump them
to Core main. Different SHAs alone do not prove incompatibility.

### Evidence boundary for this refresh

The source-adoption reconciliation checked 23 published patch blobs, 141
materialized source/artifact blobs and forward/reverse patch dry-runs against
the refs above. Ten source candidates had exact unchanged target identities.
The separate source-bundle qualification repeated archive extraction, Python
controls, source-freeze refusals and exact patch apply/reverse in independent
copies. These counts are different scopes, not a total product test count.

No new Rust/Cargo build, native tests, Core probe, hosted gate, UI or benchmark
was run. Visible empty check/status lists are not PASS. No upstream source,
dependency pins or active workflows were changed by this documentation update.

---

## Historical plan, 2026-11-15

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

