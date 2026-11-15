# Independent review of targeted runtime evidence

Verdict: the saved evidence supports two expected baseline behavioral failures and ten passing candidate tests (7 new + 2 selected fake-proc controls + 1 weighted-mean control). No blocking discrepancy found. I read the wrapper, preparation, four command/result records and all four stderr logs; I did not rerun or import project code. My own execution was limited to text inspection and stdlib file/hash/JSON verification.

## Identity and preservation

Baseline: Core `bcbda4435534a296c707a1daa250813d692f68e1` plus only the new test module. Candidate: the reviewed final patch, applied to that Core baseline. Independently verified current patch SHA256 `7a299b5a1dfd19413ce460da5515d905304c956f7456818a9a316e8a7e1f23f2`.

INPUTS-BEFORE and INPUTS-AFTER are identical. Independently recomputed every current file hash against those manifests: before 14 files, after 15, sources 14, baseline copy 15, candidate copy 15. Candidate equals reviewed after; baseline equals before plus the exact new test file. All eight stdout/stderr hashes match RUNS.json. Coordinator preparation records successful git apply check/application and 14 source blob identity checks; I did not repeat remote source retrieval or apply operations.

## Actual results

- Baseline selected subject-summary test: assertion `50.0 != 0` at the weighted CPU assertion, before new evidence fields are accessed.
- Baseline selected full-tree comparison test: assertion `'50.00' != '0.00'`. Exit 1, two failures, no test errors/import failures.
- Candidate new module: seven tests, exit 0, OK.
- Candidate selected SamplerTests JSONL/missing-memory and transient-IO controls: two tests, exit 0, OK.
- Candidate selected PreservationTests weighted mean: one test, exit 0, OK.

These are ten candidate passes and two deliberate baseline failures, not twelve passes. The observed baseline values establish the targeted synthetic attribution regression in both projections, not a fresh measurement of a real benchmark workload.

## Execution scope and limitations

RUNS records Python 3.12.14 with `-B -E -S`, separate baseline/candidate copies, explicit selected names for the existing test modules, clean environment and private HOME/TMPDIR. Only the new seven-test file is run as a whole. The wrapper executes four project test commands plus preparatory git text operations, with no installation step. Each recorded HOME/TMPDIR is empty afterward.

The inspected selected test bodies use temporary fake proc files, synthetic aggregation and controlled clocks in the new scenarios. Existing fake-proc controls still use the ordinary clock; this is not a claim that every selected test clock was mocked. No selected body invokes real process-tree measurement, cleanup, a native application, API/LLM request or Rust. Local imports include dormant process/HTTP helpers; the inspected execution paths do not call them. This is a source/path assessment, not network capture or OS-level tracing. Existing platform sandbox/copies are used; no additional OS/network namespace is established or claimed.

No historical benchmark dataset or published result is regenerated. Manifest equality covers the listed source/copy trees, not an audit of the entire filesystem. Tests do not validate real proc timing, complete lifetime accounting, arbitrary telemetry chronology, or broad performance/GUI behavior. Source-review limits on nominal intervals, missing baselines and legacy read-time projection remain applicable.

## Evidence hashes

- RUN-TARGETS.py: `74b283fb5771dcf5d0e11ef7f2d0a0b4e1354022dbbe17c1f6205699c87d764e`
- runtime/RUNS.json: `6164591f13943d16133380f08ff0c3d54108ae09934e45b07f0c980ee3e620d5`
- runtime/RESULT.json: `2b7eca1b8e822fc2f53e7c56ca3b2e3cd971c03b4bf31fc6b6bf2e551327bdb1`

This supplements, rather than rewrites, the pre-execution source review.
