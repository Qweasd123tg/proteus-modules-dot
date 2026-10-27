# Core-only foundation composition experiment

Status: prepared privately; source-only review pending; no publication or execution yet.

## Scope
Compose immutable public sources into separate fresh Core checkouts:
1. Baseline: current Core + unchanged ownership test additions + recovery tests + admission tests.
2. Candidate: current Core + PR31 ownership v7 + PR26 recovery + PR24 admission.
3. Instrumented control: the exact candidate plus a three-file additive test-only recovery/deletion control patch. This tree is never labeled production.

No new production logic is introduced. Config/image v3, optimized shipping Modules, portable packaging and native-window qualification are excluded. All original drafts remain unchanged. No merge, upstream write, release or deployment is authorized.

The controller validates every input digest, every touched original source file plus the pinned complete Git trees, all three complete in-memory composition plans and all stage trees BEFORE writing any candidate source file. It applies complete unique old hunk text with no fuzz. After materialization it stages all authored source files and verifies the exact full Git tree, ownership-delete byte retention, recovery guards, and unchanged PR24 output blobs. Source/index snapshots are checked again after all execution.

## Source and publication provenance
All production and pre-existing regression sources are ALREADY PUBLIC immutable files from:
- PR31 d92dc1b1b9ed6e95f58439e486aed94e234cc2b5, ownership/2026-10-27/conservative/candidate.json.
- PR26 1151f9f7aab6fb524f0fab04b5ad049f5a7de610, qualification manifest; unchanged recovery patches read at a0c1716756f8d5950dbf92638951f676bf8d2803.
- PR24 fc5b410592338f9633958e5378f36e5a96b61caa, admission manifest and patches.

The new publication proposal contains ONLY this README, manifest.json, check.py, the exact guarded workflow and recovery-owned-delete-control.patch. The last file is newly authored test-only source; its operational hook and deletion wrapper are cfg(all(test, unix)), reuse the actual existing I/O routines, and require independent exact-byte review. No copied 147 KiB ownership source JSON or other production source bundle is republished. manifest.json records repository, full ref, path, byte count, SHA256 and Git blob for every input.

Destination proposal: Qweasd123tg/proteus-modules-dot on ci/core-foundation-composition-20261027, additive to a0c1716756f8d5950dbf92638951f676bf8d2803. All 564 prior files must retain their modes and blobs. Publication has NOT occurred. Exact bytes require independent review and the parent's approval gate before any push.

## Fixed source identities
- Core base: 63454d4e8b1e4e6b26d088fce2a17d46f30390ae; tree 6fa614531f2f6ca82ad37a195b02bc1371d5b0bd.
- Tests-only baseline: 851614f53b37136bd3c748d8aa40177fe61af6e8; eight changed paths.
- Production composition: 7dec0c811a514adf32a70907635939547e0a57cf; twenty-four changed paths.
- Separate instrumented control tree: 5261ae89fb5c6edd2a19b7bd7e9e630a26d6aacb; twenty-five changed paths relative to pristine Core, three test-only differences from production.
- Canonical fixture Modules: 7fceaebc3bed8add9b0e3091110f59deca86ba46; tree 3ae2efb0dee236eae3b50083c97e9e2d82e34844; retained Core SDK graph bee0e409e746e2df9db32748d4f8ea02201bd4af.

The canonical fixture is not shipping Modules 0d9c5fd or its f3d01053 graph. This experiment does not qualify the optimized shipping graph.

## Required hosted gates
- Controller rejection/process-bound controls and strict composition/parser controls.
- Both baseline and candidate compile before direct-test classification.
- Admission baseline classification requires its exact reviewed Result-returning Error line; ownership/recovery baseline classification retains the original panic/marker contract. Wrong exit, unrelated failures and mixed evidence are rejected.
- Baseline: exactly twelve previously established behavioral reds and eight positives. These reuse original unchanged assertions: five ownership integration reds, one direct-handle ownership red, one recovery HTTP red and five admission reds.
- Recovery's three new unit cases are deliberately not registered on baseline and are NOT counted as baseline reds.
- Candidate: all eleven ownership integration cases; five ownership unit and four retained lifecycle/HTTP cases; all nine recovery/startup cases; full protocol package with all twenty-seven required names; all sixteen canonical real-module module_swap cases.
- Unchanged canonical `python3 scripts/test.py full`, with every mandatory component name observed as exactly one PASS, no unapproved ignores or filtered cases. Only the three existing opt-in benchmarks and two explicitly invoked child-process helpers may be ignored.
- Official Rust 1.95 formatting, source/index integrity, source snapshots including newly authored files, and independent canonical fixture snapshots.
- The instrumented library is separately compiled with its own fresh target. Only after baseline and strict production qualification, exactly one named overlap test must pass with --show-output and all four unique schedule-completion markers. A separate full instrumented Core unit suite runs under ordinary four-thread scheduling, preserving all ownership/recovery mandatory names and only the three existing benchmark ignores.
- This one new test exercises missing/malformed index × reader-first/removal-first. Handshakes occur after real journal projection and after actual deletion-worker retirement; no sleep or elapsed timeout proves overlap. Accept a coherent old revision OR an explicit missing/retry/retired error. Verify unchanged canonical bytes/open inodes, actual OS-lease retention, retired-write rejection and no session recreation. No general read-retirement linearizability, same-UUID, cancellation-extension or speed claim follows.

Only exact-head hosted execution plus artifact review can change the status. A zero exit from setup, a compile failure, unrelated panic, empty filter or timeout cannot satisfy a behavioral red.

## Runtime/resource policy
Ubuntu 22.04; official Rust 1.95.0; Node 22.18.0. Two Cargo jobs. Dedicated fresh baseline, production and instrumented targets and Cargo/npm homes. Baseline and production run in two standard jobs (matrix fail-fast false; max-parallel two). A separate fresh instrumented job starts only after both pass. Each job admits only with at least eight GiB currently free and stops below two GiB; these are experimental infrastructure budgets, not a guarantee that a lane will fit. Each controller retains its 110-minute deadline and each phase job its 150-minute bound; aggregation is limited to ten minutes. No target directories, verified binaries, system assets or preinstalled tools are manually deleted. No paid/larger runner is selected.

The former twenty-GiB admission floor had no observed prior-run disk receipt and exceeded the standard public Ubuntu runner's documented fourteen-GB storage allocation. See [GitHub's standard-runner specification](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for-public-repositories). Passing component runs did not prove the combined peak footprint. The first hosted phase receipts will record actual initial and per-command before/after/minimum sampled free bytes. Admission failure, measured low space, Python ENOSPC/EDQUOT and exact errno-annotated subprocess exhaustion diagnostics are infrastructure errors, not product regressions. Generic compiler/test failures remain gate rejections.

Every job still validates all three small source plans before any source replacement, but compiles only its selected phase into a fresh target. The canonical fixture is rebuilt separately per job against its unchanged source graph. All source/index snapshots and every original runtime gate remain mandatory. Artifact names bind the exact head, run ID, attempt and phase. A bounded, always-attempted aggregation job rejects missing, foreign, duplicate, nonterminal, infrastructure or nonpassing receipts; verifies all shared source/input/controller/manifest identities and every raw stage-output digest; reclassifies the exact baseline cases and production/instrumented required outputs; and requires all three exact outcomes. It never accepts a generic PASS field alone. Per-phase success is not aggregate qualification. A retry must rerun all required phase jobs (or use a new commit/run): successful artifacts from an older run attempt are deliberately rejected, never reused to fill a missing current-attempt phase.

All npm commands, including commands launched by unchanged canonical scripts, inherit both npm_config_audit=false and NPM_CONFIG_AUDIT=false. Explicit fixture installs use --ignore-scripts --no-audit --no-fund. No npm advisory submission or automatic dependency fix is performed. Child environments are allowlisted and do not inherit application/test tokens or arbitrary source/build overrides; ordinary network proxy infrastructure may remain.

The workflow installs only the approved official size/digest-pinned bubblewrap 0.13.1 as ordinary root-owned mode 0755. No setuid, file capabilities, sysctl, AppArmor or other security-policy change. A real namespace/FD probe and canonical Core sandbox tests are mandatory.

The workflow is guarded-push-only on its exact branch; no workflow_dispatch dependency. Evidence retains bounded per-phase result JSON, stage logs, sandbox provenance and an explicit aggregate receipt for seven days, not binaries or runtime homes. Group cleanup covers cooperating original process groups, not deliberately escaped sessions.

## Evidence limits
No product source, test, build or controller orchestration executed on the low-disk preparation machine. In-memory source/hash composition and Python AST parsing were performed; the v6 repair additionally permits only its pure parser controls and replay against hash-verified captured log text (no files, subprocesses or product imports). Independently reproducible source trees are not runtime qualification. No speed, RSS, queue-boundedness, full product integration, security remediation or merge-readiness claim.

## Canonical custom-harness accounting repair (v6)
The v5 hosted run's baseline qualified, but production remained rejected: the unchanged canonical full command exited zero, then the controller incorrectly counted 26 custom session outcomes as libtest-summary outcomes. Source-after checks and the separate instrumented phase did not run; this is not combined qualification.

This repair changes only evidence parsing/provenance, not production source, tests, assertions, or the canonical full command. Six unchanged source blobs bind the two process-host `harness = false` targets and the capability-environment helper. Full-workspace no-run discovery uses `scripts/test.py full --no-run --message-format=json` with the same effective environment/target directory immediately before `scripts/test.py full`. The three relevant compiled source/feature/executable identities and their unchanged before/after binary digests are mandatory.

Only the exact bound Cargo session section's ordered 26 outcomes and sandbox section's ordered seven PASS checks are separated; missing/duplicate/foreign outcomes and unrelated PASS lines reject. Ordinary libtest totals and all 72 existing mandatory names remain enforced. Capability-environment's three checked executions are explicitly one top-level test plus two child helpers, not three unique tests; no blanket deduplication or global subtraction of custom successes is used. The aggregator independently repeats parsing and provenance validation. A fresh complete three-phase run is mandatory; historical log replay is parser evidence only and cannot supply missing binary/source-after/instrumented receipts.
