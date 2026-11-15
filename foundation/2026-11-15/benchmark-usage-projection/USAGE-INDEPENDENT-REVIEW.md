> Publication note: this is the historical source-only stage. The later RUNTIME-SUPPLEMENT.md records six targeted synthetic tests passing on the same patch. Other gates remain unrun. References to raw evidence describe reviewed retained artifacts, not files included in this public package.

# Independent source review: shared benchmark usage projection

## Verdict and scope

No source-level blocker found for the exact F3-only candidate. A small shared usage projection is justified: the short report needs the existing long-report completion policy, not a second policy copy or a dependency on the long report's grading/report machinery. This is not a new framework and not evidence of executed correctness. No Python project import, compile, test, or script execution occurred; only source/diff reads and hashes. No historical result artifacts were rewritten.

Core bcbda4435534a296c707a1daa250813d692f68e1 is the supplied baseline. Eight-source identity catalog is coordinator evidence. Review is limited to accounting/projection; unrelated adapter mechanisms were not examined.

## Exact data-flow assessment

The extracted read_json/json_lines/known_sum/usage_completion definitions retain the existing long-report logic. project_usage obtains the same metrics provider_usage mapping, copies it into reported_usage, and projects the same default token keys plus reported keys. Exact integer reported values take precedence over partial_reported_usage_sums. Incomplete lifecycle masks tokens to None for the existing reported keys; reported_usage and observed_partial_usage retain the observations. Complete tokens are a separate dict copy, avoiding mutable alias with reported_usage. This is shallow copying, appropriate for numeric expected values, not a new arbitrary nested-data contract.

Long read_trial previously initialized tokens/observed_partial_usage from those same metrics and did not alter them before the replaced block. Its resulting JSON values therefore remain equivalent for schema-valid artifacts under the same filesystem evidence. Long summarize still selects attempt==1, retains graded versus observed denominators, and passes only its prior observed set to the identical formulas. Missing result rows do not become zero-usage rows.

Short read_rows now uses that projection rather than treating every provider subtotal as a total. Flat input/cached/output summary keys remain, but use strict known_sum semantics and lifecycle-masked row tokens. Counts and lower-bound sums are additive fields. Requests/actions retain their prior complete_sum behavior. Pair identity, duplicate-run check, exclusion filter, grouping, attempt/repeat membership, pass/grade and timing formulas are unchanged. Repeats remain separate and do not enter primary token aggregates. No benchmark execution or stored metrics are changed by extraction.

## Important limits, not new fixes

- usage_complete is the existing lifecycle classifier, not proof that every category or native usage row was reported. F4 missing native usage rows remains open; this candidate cannot reconstruct them. F1/F2 classification/formula issues are not fixed.
- known_sum requires type(value) is int and rejects bool, floats and None. known_token_runs intentionally preserves the old long formula value is not None, so it is not a strict-integer coverage validator for malformed artifacts. observed_token_sums preserves the existing fallback `partial or 0`; it does not validate arbitrary types or make absent observations measured zero. A zero observed sum with zero coverage cannot be reported as zero complete cost.
- The short report now reads the existing Pi stdout or OpenCode native evidence on classifier fallback branches. Missing files follow the extracted helper behavior; malformed native JSON or unexpected shapes can still fail. This is an added short-report read/error dependency, not all-input failure-equivalence. The long report already had these paths. Do not claim generic malformed-artifact hardening.
- The classifier can recognize completed generation despite outer pipeline failure/teardown; masking must not be simplified to pipeline_ok alone. `timed_out` remains evidence for that policy, not an unconditional veto of every fallback.
- Long JSON-value equivalence does not imply preserving Python object aliasing or exports of every former internal function. No usage_completion consumer outside the prior long-report definition/call was found in the supplied Python source corpus; no universal external API compatibility claim is made.

## Imports and proposed tests

Sibling usage_report imports fit the existing direct-script execution layout and the proposed tests' sibling imports; no report-to-report dependency is introduced in production. Both existing reports retain guarded main entry points. No import was executed.

Six proposed unittest controls appear source-consistent: common complete/partial projection and unchanged artifact bytes; primary/repeat denominators; missing category with observed partial; explicit zero versus no coverage plus token/report copy isolation; Pi/Proteus teardown completion; unchanged mismatched-input rejection. Temporary fixture names split into the expected four fields; relative() handles temporary paths outside Core; read_trial accepts the supplied fields. Test cases call existing reporting entry points, but they have NOT RUN.

Coverage does not include OpenCode fallback, malformed native artifacts, bool/non-integer legacy behavior, or every unchanged long-report consumer. These are honest limits, not a basis for asserting failure. In particular, source reading is not proof that all historic long reports regenerate identically.

## Own SHA256 checks

- shared-usage-projection.patch: c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f
- usage_report.py: 33af2511f6b3b92281c4b843b374b666ae5507fe7b257144bcee74c2d4292c74
- usage_report_test.py: 817f7f27f0284bddd1e6f5a044b87a9c62a160c84028efd441a16ce1f0537da4
- report.py: c8d97877724dc71a4056208a346c84084b376748938833355350e67b8936e8ae
- long_report.py: 6acc92aca35a03f0a9ec5cf13dde7bb4b060462661c9686b96084d3593fa8e32

No source integration/publication or runtime measurements performed. Acceptance is bounded to the reviewed source candidate and stated legacy-policy limits.

## Final extraction cleanup delta

Re-read final baseline-to-after long_report diff. Removal of the two redundant initial tokens/observed_partial_usage assignments is safe for the reviewed schema-valid path: no intervening branch reads those row fields; project_usage is now their sole owner. Blank-line cleanup adds no behavior. Row dictionary insertion order can differ, so long-report equivalence means JSON values, not serialized byte ordering. Own hashes above now refer to final patch c1c30727… and long_report 6acc92ac…; helper, tests and short report hashes remain unchanged.

Read EXTRACTION-VERIFICATION.json, which records coordinator exact text equality for the four extracted function bodies, not Python execution. The source catalog is now 12 files according to coordinator verification; supplemental consumer checks do not enlarge this review into unrelated harness behavior. No source-level blocker added; no Python imports/compilation/tests or project scripts run.

## Final report verdict

Read REPORT.md in full and independently confirmed SHA256 2c53e11b25950a2a36d0304e4b1fff51566f0ddedf584c7d4fc5548a19854c6e. No blocking overclaim found. It confines the candidate to F3, explicitly leaves F1/F2/F4 open, preserves the existing long-report classifier rather than declaring it universally correct, and distinguishes schema-valid JSON-value equivalence from byte ordering or alias identity. Caller-specific denominators/repeats, legacy non-None coverage, missing-category/zero limits, and the short report's added artifact-read/error dependency are stated accurately. No historical numbers or results are claimed to have been regenerated or corrected. Six proposed tests and their future command are clearly NOT RUN. Final patch remains c1c30727…; bounded source-only acceptance is unchanged.
