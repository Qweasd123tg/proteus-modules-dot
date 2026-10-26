# CI artifact-verifier regression controls

Eighteen standard-library Python controls for the authored strict verification
pair's CI artifact helper. Requires Python 3.11+; no Cargo, Rust binaries, SDK,
external project, service or model executes.

From the repository root, using the supplied publication paths:

```sh
python3 -B -I tests/strict-ci-controls/test_controls.py \
  scripts/verify_strict_artifacts.py experiments/strict-pair \
  validation/strict-ci-verifier-controls
```

Arguments are the **owned helper**, strict workspace and a **new output directory**.
The helper interface is `verify(workspace, artifacts, workspace_log, review_log)`.
The test imports that helper; do not point it at third-party code. All generated
artifacts and Cargo-looking logs are explicitly synthetic and retained only in
the new output directory. Bytecode writes are disabled. The original workspace
and helper source are not modified.

Every adversary first passes an unchanged baseline, then requires the intended
exact rejection diagnostic. Cases cover stale policy/profile, bool/int/float
coercion, content digest/count, missing/duplicate/wrong-pointer checks, current
call identity, contradictory positive error, leaked/unrelated negative evidence,
and missing/ignored or summary-only test logs. An assertion-order permutation is
a positive control.

**These 18 controls are not the separate 81 workspace + 8 independent Rust tests.**
They test the validator using invented records and cannot establish producer
execution, authenticity, actual Core integration or meaningful project coverage.
Run the actual strict-pair gate separately and preserve both sets of evidence.
