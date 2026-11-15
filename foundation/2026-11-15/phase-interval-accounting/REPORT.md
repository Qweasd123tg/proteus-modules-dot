# Candidate: one whole-observed-interval rule for phase CPU/IO

## Status and dedup

Bounded correction of the **known benchmark-cpu P2** in delivery PR85, not a newly discovered issue. Candidate against Core `bcbda4435534a296c707a1daa250813d692f68e1`; not applied to upstream, not a production release. Source-reviewed and then exercised by narrowly selected Python stdlib synthetic tests. No Rust execution, native benchmark, provider/API call, live measured process, or historical result regeneration.

Start and end read-only ref checks agree: Core `bcbda4435534a296c707a1daa250813d692f68e1`, Modules `c035142558f0fca43e9772fc0e50ca293abf1531`, delivery `a00519d24d16ac119302119ec405c40201a712d9` (PR128). Fourteen source blobs are recorded and Git-blob verified in `SOURCES.json` / `READ-VERIFICATION.json`. This patch targets the separate resource-measurement family. It has no changed-file overlap or source dependency on coding-harness proposals PR126–128; those proposals and their partial-usage limitations are not superseded or retested here. It does not alter the Core version pinned by Modules.

Patch: `phase-interval-accounting.patch`, SHA256 `7a299b5a1dfd19413ce460da5515d905304c956f7456818a9a316e8a7e1f23f2`.

## Root cause and common invariant

`Metrics.mark()` changes the phase label, but the next `Tree.sample()` counter interval still begins at the prior Tree observation. `Metrics.summary()` assigns that whole interval to its ending label. Separately, `summarize.py` filters raw full-tree samples by `resident_idle` and weights all resulting intervals, losing the intervening markers. Thus both views can attribute launch work to idle. The original finding and historical evidence are preserved in `PRIOR-CPU.md`; its old live-process probe was **not rerun**.

The candidate makes nominal interval eligibility explicit once:

1. Tree adds `interval_start_monotonic_ns` from its actual previous sample-start timestamp, the same boundary used for elapsed time. First observation has no start.
2. `PhaseIntervals` tracks the latest marker, including repeated names and A→B→A. An eligible sample must match that phase, have integer marker/start/end, start >= marker, end > start and positive finite duration.
3. Recorder's existing `write()` path annotates samples, including the Metrics direct-tree path. Metrics uses eligible intervals for CPU median/peak, weighted CPU and phase counter sums.
4. The raw full-tree comparison feeds **all markers and samples** through the same helper before selecting resident idle. It recomputes eligibility rather than trusting a stored flag.

Crossing intervals are excluded from attribution, not prorated or shifted into another phase. All raw counters, observed lifetime totals, memory samples/peaks and total sample counts retain their sources. Eligible/excluded sample counts, seconds and excluded observed counters expose the coverage tradeoff. No eligible interval means CPU unknown, not measured zero.

The common rule replaces two inconsistent consumer decisions, not the distinct subject/full-tree aggregation representations. It is intentionally not a general telemetry framework. Production Python files grow from 630 to 691 lines (+61); docs +39 and a new 209-line synthetic test module are also added. There is **no LOC-reduction or runtime-performance claim**. The architectural benefit is one explicit attribution rule used by both views, with provenance and nonzero/unknown controls.

## Exact behavior and historical compatibility

- Current all-phase memory and whole-case observed counters remain available even when a counter interval crosses a marker. The crossing interval's work is not erased from raw/lifetime evidence.
- Empty eligible counter sums are still numeric zero, but must be interpreted with `eligible_interval_samples` / `observed_interval_seconds`; they do not establish zero total phase cost. CPU aggregates are `None` without eligible coverage.
- `excluded_interval_seconds` sums known durations, not unknown first-sample time or every unobserved gap. Excluded counters are existing observed deltas, not a reconstruction of all missing work.
- New summaries identify `whole-observed-interval/v1`. Old saved subject aggregates are shown unchanged with a legacy notice. They are not silently regraded.
- Old raw samples lacking exact interval-start provenance yield unknown full-tree phase CPU under this new read-time projection; their memory is retained. This deliberately changes that derived CPU display to `н/д`, not the stored historical files. It is documented and tested. No previous published score is declared wrong.
- This rule is about ordered events from one Tree and one monotonic clock. It is **not** a validator for arbitrary reordered/malformed logs. Backwards markers are not globally detected; duration/start consistency is assumed from Tree production.
- Times describe nominal sampler starts and observed launcher markers. Sequential `/proc` reads are not atomic; delayed observation does not reconstruct the true earlier driver-event time. Missing per-process/counter baselines, unseen/final work and other lifetime-accounting gaps remain. Eligibility alone does not certify complete CPU coverage.
- Whole files containing unrelated live-process/cleanup tests were not executed. Their dormant imports are not a claim of tested behavior. No process-authority/security or previously excluded direction was investigated.

## Execution evidence, not a real benchmark

Independent exact source review accepted the candidate before execution. The test driver created two separate copies: raw Core plus only the new test module, and raw Core with the exact reviewed patch applied. `git apply --check --whitespace=error` passed, and the applied candidate matched `after/` byte-for-byte. Source/input/copy hashes were unchanged after execution.

Available interpreter: **Python 3.12.14**. Commands use `-B -E -S`, an explicit clean environment, private temporary HOME/TMPDIR, and existing platform sandbox. No dependencies were installed and no extra OS/network isolation is claimed. Detailed commands, environment, timestamps and exit codes are in `runtime/RUNS.json`; stdout/stderr are saved separately.

| Selection | Observed result |
|---|---|
| Raw Core: two new behavioral regressions only | Two expected assertion failures: subject idle `50.0 != 0`; full-tree idle `'50.00' != '0.00'`. No import/runtime error. |
| Exact candidate: seven new tests | 7 passed. |
| Exact candidate: selected existing fake-proc tests | `SamplerTests.test_jsonl_markers_and_missing_memory` and `test_transient_io_failure_does_not_inflate_next_interval`: 2 passed. |
| Exact candidate: selected existing weighting control | `PreservationTests.test_idle_cpu_uses_weighted_interval_mean`: 1 passed; fixture explicitly supplies eligible intervals. |

**Ten candidate tests passed.** These are synthetic controls of actual project functions with fake proc files/controlled clocks and temporary report JSON, not ten independent real workloads or an end-to-end benchmark. Existing fake-proc tests also use the ordinary monotonic clock without sampling real `/proc`.

New controls cover: crossing launch→idle in both consumers; old-phase boundary sample; stable-phase time weighting; repeated names/A→B→A; missing/empty interval evidence; legacy raw CPU unknown while saved subject CPU remains unchanged; CPU valid zero distinct from unknown; excluded RSS 400 peak retained beside eligible RSS 100 (median 250); raw crossing CPU/read bytes and lifetime CPU unchanged. The two crossing methods overlap by design to exercise both consumers. They do not independently establish broad benchmark accuracy.

No historical benchmark inputs were used or modified. Test render assertions also verify synthetic source reports and raw samples remain byte-identical. `RUN-TARGETS.py` reproduces only this narrow selection and refuses to reuse its runtime directory rather than overwriting evidence.

## Artifacts

- `CONTRACT-REVIEW.md`: independent initial source-contract analysis.
- `SOURCE-REVIEW.md`: independent exact candidate and safe test-selection review, including final revision hash.
- `RUNTIME-REVIEW.md`: independent inspection of actual commands/logs/hash evidence; separate from source approval.
- `runtime/PREPARATION.json`, `INPUTS-BEFORE.json`, `INPUTS-AFTER.json`, `RUNS.json`, `RESULT.json`: executable-evidence record.
- `DIFFSTAT.json`, `FRESH-REFS.json`, `END-REFS.json`, `SOURCES.json`, `READ-VERIFICATION.json`: source and composition provenance.

This is a practical tested fix candidate for one known attribution family. It does not claim complete resource accounting, successful full project tests, native benchmark comparability, Rust compilation, or readiness to replace upstream production without its normal integration review.
