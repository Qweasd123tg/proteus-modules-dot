# One selected cohort for offline report counting and rendering

Candidate for Core `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`. This delivery publishes a patch, not an upstream integration or a rerun of the study.

## Reproduced functional failures

Four synthetic local-JSON examples passed through the actual offline readers/renderers:

- Long-report repeated case selection counted one result twice, with token sum 10 becoming 20.
- Short-report duplicate guard used filename aliases while aggregation used actual model/effort; two aliases for the same logical trial likewise became two primary runs.
- Long-report primary Markdown ignored selected cases/arms: a custom selected task was absent from the detail matrix while unselected default tasks appeared pending.
- Long-report rows with different requested model/effort were accepted as complete and paired, but the header still declared the fixed DeepSeek Flash/high study.

No mismatch in real historical study data is asserted. These are reproductions of how the reporting functions handle synthetic inputs, not new model trials.

## Coherent bounded change

The existing selected case/arm plan now becomes the authority for both JSON and Markdown. Duplicate plan dimensions are rejected before reading artifacts. Planned, output-cap and retry cohorts each reject duplicate logical trial identities, including normalized 01/1 attempts; intentional overlap between separate cohorts remains allowed.

The short reader uses actual model, effort, case, integer attempt and arm for uniqueness, agreeing with its aggregation identity. Different real model/effort configurations remain separate. Repeat-only configurations preserve repeats and report an unknown primary median instead of crashing on an empty median.

The long reporter remains a fixed DeepSeek Flash/high study, not a newly generalized benchmark framework. Observed planned/cap/retry results must match that requested configuration. Historical comparison baseline is deliberately separate. Missing results remain pending/running; pipeline failures are retained, not silently turned into missing or passing trials.

Six behavior methods extend the existing usage-report test file. No new test framework, provider request, runner orchestration or process handling is added. Existing usage completeness, partial lower bounds, explicit zero and first-attempt/repeat separation remain unchanged.

## Verification and scope

- Six existing and six new synthetic Python methods passed in the author run and an independent fresh copy.
- The independent reviewer reproduced the original four functional failures, then requested an additional diagnostic-cohort duplicate correction before acceptance.
- Default plan with no artifacts, and a complete default plan of 40 synthetic artifacts including repeats, both retained exact Markdown bytes. JSON stayed exact except the additive selected `cases`/`arms` fields.
- Five source blobs match the exact Core tree. Strict patch application, exact candidate bytes, reverse and exact original bytes confirmed.
- No harness/model/process execution, Rust/Cargo, hosted CI or performance benchmark. No historical results rewritten; no speed/RAM claim.

Newly generated reports carry selected axes; the renderer consumes those axes. This is not a migration of previously saved JSON documents. The candidate does not redefine historical-baseline comparability, audit every prose annotation in the study-specific report, or add a general result-schema validator. Selection/configuration errors intentionally stop report generation instead of emitting misleading totals.
