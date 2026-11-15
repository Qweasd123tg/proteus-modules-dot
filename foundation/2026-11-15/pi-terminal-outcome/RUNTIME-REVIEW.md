# Independent targeted runtime evidence review

## Verdict

Evidence supports the intended behavioral red/green controls: baseline two selected tests fail on the opposite pipeline boolean assertions; candidate nine Pi tests and six updated PR126 usage tests pass. No discrepancy found. I did not rerun project code or import project modules. This supplements the earlier source-only stages, not a claim those stages already included execution.

## Independently checked

Read RUN-TARGETS.py, PREPARATION.json, RUNS.json, RESULT.json and all three stderr logs. The wrapper stages baseline from Core bcbda4435534a296c707a1daa250813d692f68e1 plus PR126, adds only the new test module, and applies final patch b2b457e7dd2cfb17e1489ef97728080c09b306d9dedd0456f5c2b65b8114a2ee to a separate candidate copy. PREPARATION records successful inert --check/apply and exact candidate equality.

Own diff checks confirm candidate == reviewed after; baseline == before except pi_terminal_test.py. Own stdlib-only JSON/hash verification (not importing or executing project files) confirms identical before/after manifests and current contents: before 8 files, after 10, sources 13, baseline 9, candidate 10. All three stdout/stderr hashes match RUNS.json.

Python 3.12.14 runs use -B -E -S, explicit environment, separate private HOME/TMPDIR and a 30-second driver timeout. Selected command identities and results:
- Baseline: only test_recovered_error_is_not_terminal_failure and test_terminal_length_is_not_clean_success. Exit 1, Ran 2, FAILED(failures=2). Failures are respectively assertTrue(False) at pipeline_ok and assertFalse(True), before new metric-field assertions. No missing module/helper or runtime ERROR explains the red result.
- Candidate pi_terminal_test.py: exit 0, all nine named controls ok, Ran 9 / OK.
- Candidate usage_report_test.py: exit 0, all six named controls ok, Ran 6 / OK. This uses the modernized boundary fixture, not byte-identical old PR126 tests.

The baseline is NOT unmodified Core; it includes PR126. Red/green demonstrates these two synthetic behavioral differences, not a native Pi regression run.

Own SHA256:
- runtime/RESULT.json: 5b4757477fea760a7d0729a260da9de8317c08ef10c7321194430db545990ef9
- runtime/RUNS.json: 9695bd65097fdcde4c4bf973e95c201d52198fe566b952fedbe0fac6a45f9e3e
- RUN-TARGETS.py: 5532b7d00de42b2b32ecbb2419aa5f860929a4c60aced523805f6841a6af94f3

## Scope and remaining limits

The inspected test/import paths exercise synthetic local metrics, pipeline and reporting functions, not native CLI, API/LLM calls, graders, benchmark datasets, installs or Rust targets. Imported runner/native support functions are not called as runners. This is a code-path/selected-command assessment, not packet capture or additional network namespace verification. Ordinary platform sandbox plus copies/environment are the stated isolation.

Unchanged source/copy hashes support preservation of staged inputs, not a universal external-filesystem audit. No historical benchmark recomputation is present in these targets. Test durations are not agent-performance measurements. No full suite or live supported Pi integration was run.

F4 missing usage rows remains open. Generic taxonomy still uses its legacy diagnostic route; no broad cross-provider F1/F2 closure follows. The continuity subcase combines count mismatch and false continuity, so its individual guard is not isolated by that test. Stored success compatibility, old missing-settlement unknown behavior, generation-versus-postprocessing distinction, and malformed-input coverage limits remain as described in SOURCE-REVIEW.md.

## Final REPORT sanity check

Read REPORT.md in full; own SHA256 c1dd90ea22e13d398b88044ac108c4108c0d5a3bdcdf305a7829d1dfd5eb092c. No blocking factual overclaim found. It correctly states baseline Core+PR126, two behavioral red failures and candidate 9+6 passes, scopes the contract to the pinned native Pi evaluator, and retains the distinction between final generation, CLI postprocessing, and billing completeness. Stored-success fast path and legacy unsuccessful traces becoming unknown are explicit; F4 and legacy string-taxonomy limitations remain open. Continuity's nonisolated subcase and +51 LOC/non-performance claim are acknowledged. No-API statements are appropriately grounded in selected inspected paths, not network capture. The source-only reviews remain historical stages supplemented by runtime evidence. No rerun or project changes performed for this sanity check.
