# Audit: coding-harness outcome and usage fidelity

## Scope and evidence

- Core reviewed at `89997df995df7c39b713e16aba216ecb19c8f497` (main rechecked at start of assignment).
- Modules cross-check at `3270dc0f894eaf4d0360306052b806099b8f5351`.
- Isolated checkout: `/workspace/shared/testing-fidelity-audit`. Source remains unmodified (`git status --porcelain` empty).
- No live provider/model call, no credentials, no publication, no changes to existing benchmark output.
- Reproductions use actual `adapters.metrics`, `runner.check_pipeline`, `report.read_rows/summarize`, and `long_report` helpers. Native events are synthetic; canonical events are synthetic schema-21 inline records read through the actual journal parser.
- One accounting comparison uses values from the repository's historical `2026-11-11-deepseek-long.json`, but writes a disposable result fixture. This does **not** assert that the existing published successful short-run tables are numerically wrong.

Run:

```sh
python3 -B /workspace/shared/testing-fidelity-evidence/reproduce_accounting.py
python3 -B /workspace/shared/testing-fidelity-evidence/test_expected_accounting.py
```

`reproduce_accounting.py` completes successfully and confirms the observed defects. The second command intentionally supplies desired-behavior assertions: **4 tests fail** against the unmodified code. Five existing adapter tests and five selected existing accounting/continuity tests pass. Logs and structured output are adjacent.

## F1. P2: recovery is graded differently for Native Pi and Proteus

Sources:

- [adapters.py 257–277](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/adapters.py#L257-L277)
- [runner.py 91–112](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/runner.py#L91-L112)
- [long_report.py 211–242](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/long_report.py#L211-L242)

Native Pi metrics retain every historical assistant `error`/`aborted` in `errors`. The pipeline gate requires the entire list to be empty, regardless of successful recovery. Proteus instead requires final successful settlements and one recorded outcome per request; a failed attempt followed by a successful retry is admitted.

Reproduction: a temporary 503, `agent_end(willRetry=true)`, `auto_retry_start`, successful assistant, `auto_retry_end(success=true)`, final `agent_end(willRetry=false)` and `agent_settled(aborted=false)`. Both processes have exit 0. Native Pi gets `pipeline_ok=false`, the equivalent Proteus trace `true`.

This is a benchmark bias in favor of Proteus on successfully recovered failures, not proof of a production retry failure. `long_report.usage_completion` similarly ORs all historical native errors permanently and cannot recognize the successful end.

The event lifecycle is supported by upstream [Pi 1.5.2 AgentSession](https://github.com/earendil-works/pi/blob/v1.5.2/packages/coding-agent/src/core/agent-session.ts), which emits retry completion; [JSON print mode](https://github.com/earendil-works/pi/blob/v1.5.2/packages/coding-agent/src/modes/print-mode.ts) subscribes to all session events. No live native recovery was attempted here.

Fix direction: separate observed failures from terminal failure. Track completed user turns and recovered retry sequences, retaining all original failures for diagnostics/usage. Apply equivalent terminal-success criteria to all arms.

## F2. P2: a final truncated Native Pi answer is reported as a clean pipeline

Same adapter/gate sources. Pi `errors` only includes `error` and `aborted`; `settled` means any `agent_end`. Final `stopReason=length` is never recorded as a failure or output-limit event.

Reproduction: final assistant `stopReason=length`, followed by non-retrying `agent_end`, exit 0. Results:

```text
pipeline_ok = true
errors = []
usage_complete = true
failure_taxonomy.classes = []
```

If code was already correct before the truncated final response, independent grader PASS can become full PASS without revealing output exhaustion. This differs from the report's treatment of terminal output-limit cases, and prevents a reader from distinguishing clean completion from truncation. It also makes a clean-series exclusion based on `model_output_limit` ineffective for this arm.

The exit-0 assumption is supported by the pinned upstream print-mode implementation: its final-assistant error/length exit check is under text mode, while the benchmark runs JSON mode. [Pi JSON event conversion](https://github.com/earendil-works/pi/blob/v1.5.2/packages/coding-agent/src/modes/json-event.ts) preserves final `message_end` data. The synthetic trace represents a **final unrecovered** length stop, not a length stop that is followed by a successful retry.

Fix direction: persist per-turn final stop reason and output-limit diagnostics. A terminal truncated generation must not silently be indistinguishable from clean success. Keep task-grade success separate from process/generation outcome, and allow recovered intermediate length events without automatically failing the whole task.

## F3. P2: short-report token totals discard completeness and promote partial observations to full totals

Sources:

- [report.py 26–36](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/report.py#L26-L36)
- [report.py 40–66](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/report.py#L40-L66)

`read_rows` drops `timed_out` and does not retain usage-completion state. `summarize` then considers any numeric provider-usage field complete, including unsuccessful primary runs. Native metrics sum finished replies, so an unfinished generation need not cause any field to be null.

Reproduction uses the saved Native Pi `journal-segments` timeout. The existing long report correctly records `usage_complete=false`, complete input null, partial input 1,400,843 and partial output 55,589. Routing those same observed fields through the unmodified short-report path produces:

```text
input = 1400843
output = 55589
(no complete/partial/lower-bound field)
```

The recorded values are a valid lower bound, not a verified full total. Short-report comparisons can therefore make interrupted arms appear artificially cheaper, even though FAIL remains correctly recorded. Existing successful historical short-run totals were not shown to be affected.

Fix direction: share the usage-completeness logic with the long report. Persist full totals separately from observed lower bounds and coverage counts; never infer complete consumption merely from a numeric subtotal.

## F4. P3 / robustness: a wholly missing usage row is dropped instead of making totals unknown

Sources: [adapters.py 239–260](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/adapters.py#L239-L260).

Both Codex and Pi adapters filter out completed messages lacking a dict-valued usage block before `sum_usage`. `sum_usage` can consequently check only the surviving rows, unlike the Core measurement helper that counts expected requests.

Synthetic Pi fixture: two completed assistant replies, only one usage block (10 input + 100 cached, 5 output). Result: `model_requests=2`, `pipeline_ok=true`, and complete input 110 / output 5 rather than unknown. The analogous Codex two-turn fixture has the same totals issue. A missing field *within* an existing usage dict correctly becomes unknown; the existing regression tests cover that case but not an absent whole row.

Boundary: no evidence that the pinned Native Pi normally omits its required usage object. Treat this as malformed/incomplete artifact robustness, lower priority than F1–F3, not a demonstrated normal provider behavior.

Fix direction: retain an empty placeholder per expected completed reply/turn, make strict totals unknown if any contribution is absent, and separately expose observed sums/counts.

## Reviewed without a new claim

Read runner, adapters, short/long report, matrix, corpus, long-corpus preparations, existing selfchecks; spot-checked CodeMode scoring and common process sampler. Did not rerun private upstream graders or live coding agents. Known replay-capabilities and stale release-gate executable findings were explicitly excluded from this pass.
