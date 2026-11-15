# Independent source review: whole phase intervals

Verdict: source-acceptable bounded correction of the known phase-attribution defect. No blocking issue found in the exact candidate. This is not execution evidence. I did not import, compile or run project code or tests, launch processes, or recompute historical measurements.

Reviewed patch SHA256: `73ef7e2b6172e944eab35c803d78c1dd2373d73be6a9daad12c0d2d7da90fa22` (independently hashed). Baseline is Core `bcbda4435534a296c707a1daa250813d692f68e1`; coordinator catalogs 14 source blobs. Git/source identity verification is coordinator evidence, not a fresh independent remote lookup here.

## Boundary and integration

- Tree emits its actual previous sample-start timestamp before updating previous_ns. This is the same nominal boundary used for elapsed seconds, not a previous-logged-sample heuristic or a floating-point reconstruction.
- PhaseIntervals owns only the latest observed marker. Every marker resets the boundary, including repeated labels and A→B→A. Matching phase, exact integer timestamps, start >= marker, end > start and positive finite duration are necessary. Equality at the start is intentionally admissible.
- Recorder.write is the common annotation point, including Metrics' direct tree.sample path. Metrics retains that flag in small samples. CPU median/peak, weighted CPU and phase counters use only eligible intervals; memory and lifetime totals retain their original sources. Excluded counters/time and sample counts expose the discarded attribution rather than allocating it to another phase.
- summarize feeds the entire marker/sample stream to the same tracker before selecting resident_idle. It does not trust a saved eligibility flag or filter away intervening markers. Raw samples without start provenance remain CPU-unknown while memory remains available.
- Stored subject aggregates are not recalculated. The policy notice explicitly distinguishes these legacy values from the new raw full-tree read-time projection. No historical input-writing change is present.

## Limits that remain important

This proves nominal whole-observed-interval attribution for ordered single-Tree, single-clock streams, not exact counter acquisition times or complete accounting. Sequential proc reads, missing baselines, unseen processes and final unsampled work remain existing limits. The latest-marker tracker is not a global chronology validator: backwards/reordered markers and arbitrary malformed telemetry are outside the documented contract. Excluded seconds do not measure all missing time; zero counters over no eligible samples are not measured zero work. CPU unknown is correctly represented by None when there is no eligible interval.

## Planned tests and execution scope

Read all seven new methods and the three specifically selected existing methods. The two proposed baseline-red cases assert the old observable weighted CPU (expected new zero versus old 50), before accessing new fields. The remaining controls cover the old-phase boundary sample, repeated/A→B→A markers, unavailable intervals, legacy raw projection versus unchanged stored subject value, same-phase weighting, and retention of all memory samples. These are source-plausible expectations, not reported passes.

New tests use private temporary fake proc files and controlled monotonic clocks. The selected existing JSONL/missing-memory and transient-IO tests also use fake proc directories; the selected weighted-mean test constructs Metrics without a real Tree. Imports are stdlib plus local modules; the selected bodies do not invoke subprocesses, HTTP, native binaries or cleanup. Other tests in those files do exercise live processes or exec paths: selection must remain explicit, not whole-file discovery. Local modules contain dormant functions for those operations, which should not be confused with selected test behavior. No independent runtime isolation or network-capture claim is made.

The tests' memory controls demonstrate preserved memory aggregation, but do not isolate an excluded high-memory crossing sample as its own peak control. Source inspection nevertheless shows memory aggregation still uses all samples. This is a nonblocking coverage limitation.

## Independently read candidate file hashes

- common/proc_sampler.py: `a896ede27436fc62896b5af219b195a1d2a960c2b9f00a32ba02af4dc72d9146`
- common/README.md: `552182ddcdc321b300b3277d9eb3e725a9673797bd2cc27125e89c427bf90115`
- history-scale/measurement.py: `758d1987a17b43e40f5c4bbea09d1e3e05af18f22312708b713fea4576e21f90`
- history-scale/test_phase_intervals.py: `c5e084c5ecf957549c48ae9e81d68f5fdb7ddfd812f24bf0c47c7628c33d642f`
- history-scale/test_harness.py: `7f010ec0b4e5aa57700765e35150237fde056ef072bb4aba62d146569bd1d8a2`
- history-scale/README.md: `9c7e53968439fc72b3278014527f25f4c915420440ab833484aa50db239030af`
- summarize.py: `a1ca5c51c49dca8eb2ddff7cb67e027757b670bd46268049627e43f722210df3`

## Final pre-execution revision

Independently re-read and hashed the final patch: `7a299b5a1dfd19413ce460da5515d905304c956f7456818a9a316e8a7e1f23f2`, superseding the initial hash above. The notices heading now accurately describes limitations/incomplete data rather than calling every excluded interval an unfinished run. The scenario accepts boundary_rss, restores the later sample to RSS 100 with unchanged CPU 100, and its first test sets crossing RSS 400, asserting median 250 and peak 400. This resolves the nonblocking excluded-memory-peak coverage limitation above. Other scenario defaults remain unchanged. Verdict remains source-acceptable; all tests still NOT RUN by this reviewer.

Updated file hashes: test_phase_intervals.py `57f449a73e9ef2972e75cba7730881b9237e592c6e6a9a205a41dadc8e04e095`; summarize.py `828358bcdcc5a2031664a170077231c484b906d8de0a72961d4fb62f6afef45b`.
