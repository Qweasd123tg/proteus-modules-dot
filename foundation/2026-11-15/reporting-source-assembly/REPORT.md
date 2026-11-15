# Python reporting integration: exact source assembly and targeted synthetic checks

2026-11-15 UTC. **Reviewed candidate assembly, not a new real benchmark or a
production-qualified release.** No upstream files, saved benchmark artifacts,
scores, tables or dependency pins were changed.

## Result and exact base

The selected #126 → #127 → #128 chain composes with independent #129, #130 and
#143 on fresh Core `bcbda4435534a296c707a1daa250813d692f68e1`. The same 22
changed files result in both checked orders:

1. 126, 127, 128, 129, 130, 143.
2. 143, 130, 129, 126, 127, 128.

All 22 targets are byte-identical to their corresponding already published
final candidates. There were no manual conflict resolutions or new production
edits. Both orders and the combined patch passed zero-fuzz text application;
the combined patch reversed to all 24 baseline/reference files, removing nine
added files. The materialized subsets contain 33 candidate files and are not
complete Core checkouts. Other possible orders were not checked.

Delivery snapshot: `e3c8b7d9bc69f22cbc58a8909c4de41f75586495`.
30 exact Git blobs were verified: 24 Core files plus six published patches.
Modules remains `c035142558f0fca43e9772fc0e50ca293abf1531`; these are Core-side
Python changes, not changes to Modules' Core runtime dependency pin.

`combined-reporting.patch` SHA-256:
`06cf01196439e8fc1ccc7a36459ff074116bedbf927f5010f48d9a2b410fdd7b`.

It is an **alternative to all six selected originals**, applied to the exact
unpatched Core base, not an additional seventh patch on top of them. Full diff
is +1377/−111 across 22 files, including tests and documentation. This is not a
LOC-reduction claim. #141 is explicitly excluded; #133 and other unselected
reporting/build candidates are not implied to be integrated or superseded.

## Dependencies and source-level boundaries

The published paths are under `foundation/2026-11-15/`:

| PR | Selected patch | Relationship |
| --- | --- | --- |
| 126 | `benchmark-usage-projection/shared-usage-projection.patch` | Creates shared short/long usage projection and aggregation. |
| 127 | `pi-terminal-outcome/pi-terminal-on-pr126.patch` | Requires 126's helper; changes its Pi fallback and one lifecycle test fixture. |
| 128 | `native-usage-cardinality/native-usage-on-pr127.patch` | Selected against 126+127, including adapter/README context. |
| 129 | `phase-interval-accounting/phase-interval-accounting.patch` | Separate resource-attribution files, no changed-file overlap with the chain. |
| 130 | `grader-module-registration/grader-module-registration.patch` | Separate journal loader and controls, no changed-file overlap. |
| 143 | `module-bundle-path-identity/module-bundle-path.patch` | Separate builder argument boundary and mocked controls. |

Exact patch blobs and hashes are in SOURCES.json. DEPENDENCIES.json records
the overlapping paths and checked orders. No forced universal abstraction
was added to make independent families appear to be one subsystem.

### Usage projection, terminal evidence and row cardinality

#126's common projection retains reported numbers and partial observations
separately from lifecycle-complete totals. #127 supplies one Pi terminal
reducer to adapter/runner and report fallback: earlier recoverable diagnostics
do not determine final success, and final length/missing terminal evidence do
not become clean success. #128 makes complete token fields require all
expected completed-event usage rows, while retaining field-level observed
subtotals. The combined native report control exercises their conjunction:
a completed lifecycle can still have unknown full token totals and a usable
partial subtotal.

This preserves the distinction between pipeline success, lifecycle evidence,
category coverage and billing completeness. It does not establish complete
billing or a universal validator for malformed event/artifact schemas. The
stored pipeline_ok fast path remains; existing saved results are not silently
reclassified. Short/long caller selection, primary-versus-repeat policy,
identity guards and original numeric policies remain those of the proposals.
An observed sum of zero without coverage does not prove zero full usage.

The six usage tests are the version retained after #127's fixture update,
not an additional untouched copy of #126's original six. No installed Pi,
Codex or OpenCode version/behavior was checked.

### Other independent families

- #129 shares one whole-observed-interval eligibility rule between subject
  aggregation and raw full-tree comparison. Crossing intervals are excluded
  from phase attribution, not reconstructed or prorated. Raw/lifetime counters
  and memory evidence remain. Old raw data without interval provenance yields
  unknown derived phase CPU, while saved subject aggregates are retained with
  a legacy notice. This is a documented read-time policy, not retroactive
  mutation of historical artifacts or proof of total CPU/IO coverage.
- #130 registers dynamically loaded journal-grader modules before execution
  and restores the exact previous sys.modules binding on BaseException.
  Successful loads still replace that binding freshly. Cleanup is only for
  that binding, not rollback of arbitrary imports/side effects or concurrent
  import locking. Assertions and broader grader qualification are not replaced
  by the six loader tests.
- #143 resolves the caller's bundle destination before forwarding arguments
  with a different child cwd. It retains existing return/exception behavior.
  The tests inspect command construction with the packager call mocked; they
  do not verify delivered files. Absolute-path spelling can normalize through
  resolve, and symlink/racing-filesystem behavior is not covered.

## Actual execution and honest counts

After independent source and exact-driver review, the assembled candidate
was tested in separate owned copies using **Python 3.12.14**, `-I -B -S`,
stdlib only. The controller ran 13 explicit target selections, not suite
discovery. Each selection used a separate interpreter. Test bodies were not
changed during this assembly.

| Candidate target | Passed test methods |
| --- | ---: |
| Shared usage projection | 6 |
| Pi terminal outcome | 9 |
| Native usage cardinality | 7 |
| New phase interval controls | 7 |
| Selected existing fake-proc controls | 2 |
| Selected existing weighting control | 1 |
| Journal loader controls | 6 |
| Mocked bundle argument controls | 5 |
| **Total** | **43** |

All 43 candidate methods passed, with no failures, errors or skips. They are
43 distinct selected methods on this combined source tree, not the sum of
historical overlapping 6/15/22/etc. totals. Subtests are not extra methods.
The families remain bounded controls, not 43 independent real workloads or
an end-to-end benchmark.

Nine baseline method executions establish the selected regressions:

| Baseline | Observed result |
| --- | --- |
| Core + #126, two #127 controls | Two expected assertion failures: recovered error gives false pipeline success predicate; terminal length incorrectly gives true. |
| Core + #126 + #127, two #128 controls | Two expected assertion failures: input total is 110 instead of unknown after a missing entire usage row. |
| Raw Core, two #129 controls | Two expected assertion failures: phase CPU 50.0 instead of 0, comparison `50.00` instead of `0.00`. |
| Raw Core, two #130 controls | Two expected loader errors from dataclasses' missing module namespace, not assertion failures. |
| Raw Core, one #143 control | One expected assertion failure: argv element 5 is literal relative `delivered runtime`, not the caller-resolved destination. |

Thus **52 method executions = 43 passes + 7 expected assertion failures +
2 expected loader errors**. Nine baseline methods repeat candidate methods;
they do not create nine additional unique tests. #126 has no new baseline-red
claim in this pass. Historical results are background only, not added to these
counts.

## Isolation and what the checks actually exercise

The controller verifies exact source/patch hashes before staging and checks
all source/copy hashes after execution. Baseline variants differ only by the
specified prerequisites and the exact new regression test files. Private
HOME/TMPDIR directories were empty after each selection. No dependencies were
installed and no existing evidence directory was overwritten.

The thin child entry inserts the selected test directory, runs the exact
script as __main__, and verifies the paths/hashes of its known project imports
in finally, including expected-red exits. Dynamic loader tests also verify
their own loaded file paths. Concrete baseline diagnostics are checked, not
merely nonzero exit codes. INPUTS-BEFORE/AFTER, RUNS, stdout/stderr and RESULT
retain the evidence. Runtime timestamps/durations are test execution records,
not performance measurements.

- Reporting controls use synthetic event/result files and actual selected
  project reducers/projections. They do not run native agents or providers.
- Phase controls use private fake proc files. New scenarios use controlled
  clocks; two existing fake-proc tests use ordinary monotonic clocks. No real
  process is sampled and no live-process/cleanup suite is selected.
- Loader controls use actual grader loader functions with our own synthetic
  modules and a pytest declaration-decorator stub. One actual consumer-test
  body receives trivial synthetic archive/measurements implementations. This
  is not the full pytest grader, a submitted/reference solution run, or a claim
  that the trivial archive meets the task.
- Bundle controls mock check_output before invoking the builder. The actual
  source resolver, packager, Cargo and any install/delivery are not executed.

Some imported project files contain dormant launch/cleanup/API functions;
their presence/import is not execution or review of those paths. The work
does not investigate excluded security/process-authority directions. Existing
platform sandbox and isolated copies are used; no additional OS/network
namespace or packet tracing is claimed.

No real benchmark, historical-table regeneration, provider/API call, native
CLI, build, installation, full project suite, full pytest suite or Rust run
was performed. Standard test-controller Python subprocesses and system patch
commands did execute. The project-wide and release gates remain outstanding.

## Handoff

The source assembly and this explicit synthetic gate are suitable evidence
for reviewing the combined alternative. They do not certify full benchmark
accuracy, all malformed input handling, all candidate combinations, current
native versions, distribution compatibility or production readiness. Keep
the original proposal limits and the unrelated HOLDs open. No new finding,
score correction or upstream merge is asserted by this package.
