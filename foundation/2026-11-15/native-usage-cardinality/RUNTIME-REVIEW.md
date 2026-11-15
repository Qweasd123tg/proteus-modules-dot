# Independent F4 targeted runtime evidence review

## Verdict

Evidence supports the reported scoped red/green result on final patch bc59d34fd938485e8a9831c87d3c6e30a4e36b01814c52f37e538d4a40cc91ef: two baseline behavioral assertion failures; candidate seven native-usage controls plus nine Pi and six usage-report regressions pass. No discrepancy found. I did not rerun tests or import project modules.

## Evidence and identity

Read RUN-TARGETS.py, runtime/PREPARATION.json, RUNS.json, RESULT.json, and all four stderr logs. Baseline is Core bcbda4435534a296c707a1daa250813d692f68e1 + exact PR126 + PR127, not clean upstream Core. Only native_usage_test.py is added to baseline; its implementation is not. Candidate is built through inert git apply --check/apply and compared with reviewed after.

Own diff confirms candidate == after and baseline == before except the new test module. Own stdlib-only JSON/hash check confirms INPUTS-BEFORE == INPUTS-AFTER and current contents match all five groups: before 10 files, after 11, sources 7, baseline 11, candidate 11. All four stored stdout/stderr hashes match RUNS.json. This verifier read source bytes as data only.

The baseline selects exactly the named Pi/Codex missing-whole-row tests. Both stop at assertIsNone(provider_usage.input_tokens) with AssertionError: 110 is not None, before new-field access. Log reports Ran 2 / FAILED(failures=2), exit 1, no import/runtime errors. Candidate logs name all seven native-usage tests, nine Pi outcome tests and six shared-usage tests, each ok, with respective Ran 7, Ran 9, Ran 6 / OK and exit 0.

Commands use Python 3.12.14, -B -E -S, isolated copy cwd, explicitly supplied PATH/locale/private HOME and TMPDIR. Driver has a 30-second timeout per target; records show empty private directories afterward. No additional OS/network namespace is claimed. Git preparation is not project execution.

Own SHA256:
- runtime/RESULT.json: 0256ff23afd1d88cfd7b035c44ac10fce3e1b55ba3b8b6f65b48364b2f5fc0a0
- runtime/RUNS.json: 197ec56d0ba1559d09d84f79526319e9071659baa9d980abaa48521472eac3b3
- RUN-TARGETS.py: 192a00f45013519a753b63261ff0325739c818e85c0d40aba93027e5ae30c450

## Limits

These synthetic fixtures establish observed completed-event robustness, not that real pinned Pi normally omits usage. The tested call paths use local synthetic metrics/report functions and stdlib/sibling modules; no native CLI, API/LLM, grader, benchmark regeneration, dependency installation or Rust target is invoked. This is source-path/command evidence, not packet capture or an audit of every external file.

Preserved staged-source/copy hashes support the stated no-change scope. They do not constitute a universal historical dataset audit. Test timings are not performance benchmarks. No full suite/live-provider integration or all-input compatibility proof follows.

The denominator remains observed Pi assistant completions/Codex turn.completed events; missing entire events, active requests and absent auxiliary usage remain undetectable here. OpenCode gets only its compatible full-total wrapper, not a new event-cardinality guarantee. Negative-int policy, non-validator limits, lifecycle/usage separation and historical-score non-rewrite claims remain as in SOURCE-REVIEW.md. Earlier NOT RUN statements refer to the preceding source-review stage and are now supplemented only for these exact targets.

## Final report and README terminology check

Read REPORT.md in full; own SHA256 fc0883adb4418d925d7fe80c4c645adde1771f938b12e5c69fe211cf084e9b19. No blocking factual overclaim found. It correctly totals 22 candidate tests (7+9+6), separates the two expected baseline failures, and confines the fix to observed completed-event robustness. Composite conservatism, negative-int policy, extra wrapper allocations, dependency order and unchanged historical metrics are explicit.

The inherited README phrase about numbers retained in reported_usage is imprecise in isolation but not a blocking contradiction in this package: the report explicitly identifies reported_usage as the adapter's strict provider_usage, not raw native blocks. The new README section distinguishes raw native_usage from partial evidence. The clarification is sufficient without another code/test/patch revision; do not claim the old erroneous numeric full total itself survives in reported_usage after cardinality masking. Raw blocks and qualifying partial sums remain its evidence. No rerun or project changes made for this final read.
