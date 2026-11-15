> Sanitized publication copy. Raw logs, launcher, execution environment paths and private artifacts are deliberately not published. Named original evidence and hashes below refer to retained review inputs, not bundled files.

# Independent review of targeted F3 runtime evidence

## Verdict

The supplied evidence supports one successful run of the six synthetic usage_report_test.py tests against the exact reviewed candidate. No discrepancy or blocking evidence issue found. This supplements, and does not rewrite, the earlier source-only review stage. I did not rerun tests or import project modules.

## Command, identity and result

Read RUN-TARGET.py, PREPARATION.json, RESULT.json, stdout/stderr and both before/after manifest pairs. The launcher checks the patch hash, verifies the three baseline file Git blobs against the catalog at Core bcbda4435534a296c707a1daa250813d692f68e1, copies them, applies the patch, and asserts the resulting five files equal final after/. It invokes only:

`python3 -B -E -S examples/performance/coding-harness/usage_report_test.py -v`

RESULT records Python 3.12.14, the separate isolated-copy cwd, an explicit clean environment with private HOME/TMPDIR, a 30-second launcher timeout, returncode 0, and empty stdout. stderr names all six expected test methods, each ok, followed by `Ran 6 tests in 0.009s` and `OK`. The test identities correspond to the previously reviewed six controls: row parity, primary/repeat masking, missing category, zero versus absence/copy isolation, teardown completion, and pair identity rejection.

Own SHA256 checks:
- exact patch: c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f (matches candidate evidence)
- RESULT.json: 1553d796e4cfc82bdb42c27762b526357201e6c4900d287baa243e79ee662977
- RUN-TARGET.py: 6a57886c229ee147e1a39703208f7caf61ef4222a7d41025239acaa9ea751d92
- stderr.txt: 218352cff1fae7f742e20a25ddf8322ea8b948f0294835cbaa867c8f520e57f9
- stdout.txt: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

## Independent preservation checks

Both candidate before/after manifests are identical, as are both original-artifact manifests. Independently recomputed current file SHA256 maps with a small reviewer-owned stdlib-only hashing/JSON snippet: all five isolated files match CANDIDATE-AFTER, and all 36 original artifact files match ORIGINAL-ARTIFACT-AFTER. Independently diffed isolated against final after/: identical. Thus the evidence supports unchanged reviewed source and original evidence artifacts through this run. Private home/tmp currently have no entries. This is not an audit of arbitrary external filesystem state.

The imported test dependencies are stdlib plus the three sibling report modules. Production report imports have guarded main entry points. long_report's dynamic history journal loader is inside canonical_records, not an import-time dependency; these read_trial fixtures are Pi, while the Proteus completion control calls usage_report directly. No native CLI, provider/API, runner, grader execution or dependency installation is present in the exercised test source. The launcher uses git only for inert patch preparation, not an additional project target.

## Isolation and coverage limits

This was an ordinary platform-sandbox run in a separate copy, not a verified additional OS/network namespace. The coordinator reports that optional bwrap preflight failed before project code with NETLINK_ROUTE Operation not permitted; that preflight is not recorded by RUN-TARGET.py and is not counted here as a project test execution or successful isolation control. Clean environment and -B/-E/-S are not claims of network confinement.

The successful narrow run improves evidence for F3 only. It does not validate OpenCode fallback, every malformed-artifact/type path, F1/F2 classification, F4 missing native usage rows, historical benchmark regeneration, all long-report consumers, Rust compilation, native processes, or live model usage. The historical benchmark data was not regenerated; preserved original-artifact hashes and the synthetic fixture scope support the limited no-change claim. No broad accounting-correctness or production-integration claim is justified.

Earlier reports truthfully describe their earlier no-runtime stage. The appropriate new statement is: six targeted synthetic Python tests now passed on this exact candidate; all other source-review limitations remain.

## Runtime supplement sanity check

Read RUNTIME-SUPPLEMENT.md in full; own SHA256 088e22a379f38952ac73a36586b75e18cd1d154e31a40ea18ea105fa5f78696b. No factual blocker found against the reviewed evidence. The no-external-call statement is explicitly limited to the inspected target/import paths and chosen invocation, not packet capture or new namespace confinement. Original artifact preservation corresponds to the 36-file manifests checked above; it is not historical benchmark recomputation. The supplement correctly disclaims baseline/red-green execution, broad suite coverage, and performance conclusions.

Also read the newly retained ISOLATION-PREFLIGHT.json: its command targets only Python --version, exits 1 with the stated NETLINK_ROUTE failure, and contains no project target. CORE-REF.json records the stated bcbda443… main identity; ref freshness remains coordinator retrieval evidence. This supplements the earlier coordinator-only preflight note without claiming an independently executed isolation check. No rerun or project changes were performed.
