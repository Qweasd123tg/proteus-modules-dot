# Benchmark-scenarios follow-up

Pinned Core/main: `89997df995df7c39b713e16aba216ecb19c8f497`, verified against remote immediately before and after reproduction. Source checkout `/workspace/shared/benchmark-design-audit` remains clean. No provider calls, user sessions, production edits, commits, or publication.

## P2: phase CPU/IO accounting includes work from the preceding phase

Location: `examples/performance/history-scale/measurement.py:64–78`, with origin at `mark():34–35` / `sample():37–47`. `Metrics.mark()` changes only the label. The next Tree sample still computes counters over its full interval since the previous sample. `Metrics.summary()` assigns all of that interval's CPU and IO to the NEW phase, without testing where its preceding sample or phase marker lies.

Permanent source links:
- [aggregation](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/history-scale/measurement.py#L64-L78)
- [idle transition in the actual runner](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/history-scale/resume_idle.py#L138-L140)
- [active transitions before the next sample](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/history-scale/active.py#L113-L119)
- [summary consumes this value](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/summarize.py#L118-L125)
- [independent duplicate issue in full-tree resident-idle calculation](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/summarize.py#L132-L145)

### Deterministic reproduction through unmodified helpers

`python3 /workspace/shared/benchmark-scenarios-evidence/reproduce_phase_cpu.py`

The repro uses the real `Metrics`, `Recorder`, and `Tree`, a fake `/proc` tree, and a controlled monotonic clock. Timeline:

1. t=1s: `mark(first_launch)`, sample CPU=0 ticks.
2. t=2s: process has consumed 100 ticks (1 CPU-second) entirely during launch; `mark(first_resident_idle)`, sample.
3. t=3s: sample CPU remains 100 ticks, so the entire true idle phase consumed zero CPU.

Current result: `first_resident_idle` = **50%**, 100 CPU ticks; `first_launch` = 0 ticks.
Positive control: insert a sample under the old phase immediately before marking idle. Same workload now produces **0%** idle CPU, launch100/idle0 ticks. Memory numbers are unaffected.

Full traces and summaries are in `phase-cpu-result.json`. Regression `test_phase_boundaries.py` has one desired-behavior test that fails (50 != 0) and one passing boundary-sample positive control. Output: `regression-output.txt`.

### Live owned-process reproduction

`python3 /workspace/shared/benchmark-scenarios-evidence/live_phase_cpu.py`

Our own synthetic Python child consumes 0.25 CPU-seconds, signals completion, then blocks reading stdin throughout the idle phase. Unmodified transition produced **47.6978% resident-idle CPU** / 24 idle ticks. With a sample immediately before the phase change: **0% resident-idle CPU** / 0 ticks, launch25 ticks. Evidence: `live-phase-cpu-result.json`.

This is not just the documented limitation of unseen short-lived children or missed peaks. Observed work is actively assigned to the wrong phase. It can create false idle-CPU regressions or improvements, especially with short phase durations, long sampling intervals, or many active peers. The same grouping applies to phase read/write byte counters. Whole-case observed lifetime totals are not invalidated by this finding.

A conservative fix is to treat intervals crossing a phase transition as ineligible for phase CPU/IO, preserving memory samples and whole-case counters. Alternatively record explicit boundary baselines. Both producer summaries and the duplicate full-tree CPU path in `summarize.py` need consistent treatment. It is unsafe to fractionally prorate counters across a boundary without an explicit approximation label. Asynchronous driver-event observation also means an arbitrary late boundary sample cannot reconstruct the true historical event time.

No assertion is made that any particular published historical memory/CPU number is wrong: those raw samples were not available in this checkout. The live controlled reproduction confirms current helper behavior, not a full production workload measurement.

## Checks and scope

- `python3 -B -m unittest discover -s examples/performance/history-scale -p 'test_*.py' -q`: **15 passed**.
- `python3 -B -m unittest discover -s examples/performance/common -p 'test_*.py' -q`: **5 passed**.
- Desired regression: **1 fails / 1 positive control passes**.
- Code reviewed: common sampler, history-scale measurement/active/idle/verifier/runner; multi-agent runner/legacy sampler; code-mode measurements/fixture/server/runner; summarize; journal-recovery runner; session-db memory runner; build-iteration runner; coding-harness matrix/corpus/short-report paths.
- Prior Pi retry/length/usage, short-report completeness, journal import, ledger interception and long-report comparability defects were not counted as new.
