# BeforeModel instructions are missing from usage telemetry

## Result: confirmed P2, separate from terminal/error usage loss

The shipped `codex_base_instructions` hook adds the model's base prompt to the **actual request**, but `TokenUsageUpdated` estimates the workflow's **pre-hook copy**. In the current Codex assembly, `instructions=[]` and the public base template is supplied by that hook, so the emitted breakdown has no `instructions` category at all. The durable model request and captured HTTP body do contain it.

Provider-reported actual usage is **not lost or corrupted in this finding**. The defect is the estimated request total and category attribution. With missing provider usage, which the canonical contract explicitly permits, the inaccurate estimate is the only snapshot value available. The context-map telemetry reader copies these fields without recomputing them. No native GUI screenshot is claimed.

Verified 2026-11-13 against remote and local HEAD:
- Core `89997df995df7c39b713e16aba216ecb19c8f497`.
- Modules `3270dc0f894eaf4d0360306052b806099b8f5351`, pinned Core dependency `b5fac84245b075896c24763b3aebac79b4375c2e`.

## Reproduction: seven complete native process chains

`run.py` launches the real Core stdio server, process `coding.codex_loop`, `codex_context`, native OpenAI Responses model module, and the selected production hook. The provider is a loopback-only HTTP/SSE fixture. It returns two completed text messages and a valid complete terminal response. No live credentials, external model calls, production edits, publication, or installation.

| Selected instruction source | HTTP/journal instruction bytes | Expected instruction estimate using the current estimator | Emitted instruction estimate | Emitted total estimate |
|---|---:|---:|---:|---:|
| None | 0 | 0 | 0 | 107 |
| `codex_base_instructions`, default | 20,903 | 5,227 | **0, category absent** | **107** |
| `codex_base_instructions`, `gpt-6.1-sol` | 21,779 | 5,446 | **0, category absent** | **107** |
| `hook.instructions`, 40,000 ASCII bytes | 40,000 | 10,002 | **0, category absent** | **107** |
| Identical 40,000 bytes via `[[instructions]]` | 40,000 | 10,002 | 10,002 | 10,109 |
| No hook, provider usage omitted | 0 | 0 | 0 | 107 |
| Codex default hook, provider usage omitted | 20,903 | 5,227 | **0, category absent** | **107** |

All seven turns succeed. Every usage_summary row reports completed / Stop. Supplied actual counters survive unchanged in both usage_summary and TokenUsageUpdated. The no-usage controls correctly retain null, not invented zero. Synthetic provider input counters are `123 + instruction_bytes / 4` and output 45; these are fixture counters, not measured tokenizer counts or billable tokens.

The 40,000-byte matched control isolates **where the same instructions enter the pipeline**, not a tokenizer approximation. The comparison uses the exact current estimator's `(UTF-8 bytes + 8 * blocks) / 4` formula, not a claim that bytes/4 is the true provider tokenizer.

## Causal path

1. Current Codex assembly explicitly clears inline instructions and selects `codex_base_instructions`: [Core config fragment, lines 3–8](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/configs/fragments/codex-upstream.toml#L3-L8).
2. The hook inserts the actual base template on BeforeModel: [base_instructions.rs, lines 30–49](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/hook/codex-context-preparation/src/base_instructions.rs#L30-L49).
3. Core owns and transforms a request copy, reshapes it, then journals and executes the transformed request: [hooks.rs, lines 27–51](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model/hooks.rs#L27-L51), [bound_model.rs, lines 295–314](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model.rs#L295-L314).
4. The response does not return that transformed request. Codex workflow emits telemetry against its original request: [codex_sampling.rs, lines 61–64](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/codex_sampling.rs#L61-L64). The shared complete helper used by single_loop and plan_execute_review has the same source pattern: [host.rs, lines 328–341](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/host.rs#L328-L341). Those two other workflows were not dynamically exercised here.
5. The estimator only sees `request.instructions`: [token_accounting.rs, lines 9–48](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/token_accounting.rs#L9-L48). App context telemetry forwards the result as latest_usage: [telemetry.rs, lines 148–172](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/context_map/telemetry.rs#L148-L172).

## Fix direction

Compute request-derived accounting after the final BeforeModel transformation/shaping, or return provider-neutral prepared-request accounting facts to the workflow and correlate them with the response. Preserve phase attribution and keep provider usage separate from estimates. Do not teach the workflow specific hook IDs or duplicate the Codex template; arbitrary valid ModelContext transformations have the same boundary.

Keep regression controls for identical instructions entering through inline configuration vs hooks, model-specific templates, and absent provider usage. The durable request already contains the correct evidence and need not be weakened or repaired.

This pass does **not** claim actual context overflow or an incorrect monetary total. Preflight compaction occurs earlier in the pipeline, but no full-window acceptance test or native GUI run was performed. The proven effect is request telemetry/instruction attribution.

## Verification and artifacts

- `python3 -B run.py`: seven end-to-end process sessions, seven loopback HTTP requests.
- `python3 -B verify.py`: all captured expected observations pass; validates captured HTTP, journal, terminal outcomes, and usage snapshots.
- `python3 -B verify.py --expect-correct`: intentionally fails the desired equality invariant for four hook cases. This is a captured-output regression check, not a production patch.
- Existing compiled targeted suites: three request-token snapshots, one Codex retry/usage event test, four effective-estimate tests, one base-instruction selection test, and 158 model-pack tests: **167 passed, zero failed**. Exact commands and binary hashes are in `baseline-commands.txt` / `provenance.json`. Existing test executables were run directly without rebuilding; this is not a fresh full workspace gate.
- `analysis.json` contains the compact machine-readable comparison. Raw app-server outputs, durable journals, synthetic configs, request captures and stderr logs are included.
- No production code changes or push/PR were performed. This is not a claim to have read every line of all repositories.
