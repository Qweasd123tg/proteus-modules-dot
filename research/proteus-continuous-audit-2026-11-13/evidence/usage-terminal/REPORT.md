# Supplemental robustness probe: partially omitted Responses terminal output

## Scope / status

Eight real Core→process coding.codex_loop→native OpenAI→loopback SSE→journal/usage_summary scenarios were run against Core `89997df995df7c39b713e16aba216ecb19c8f497`, Modules `3270dc0f894eaf4d0360306052b806099b8f5351` (remote HEAD verified 2026-11-13).

**This is an intentionally inconsistent transport fixture, not a demonstrated normal OpenAI response or a separate high-priority production defect.** The provider's complete terminal response should represent its output. We deliberately remove all or part of that array to test the existing native fallback. There is no live-provider incidence evidence. The partial cases are reported because the mapper explicitly claims to repair incomplete terminal output, while its actual behavior only repairs wholly empty/non-emittable output.

## Observed matrix

The local SSE emits FIRST_MESSAGE and SECOND_MESSAGE, then terminal usage123 input/45 output. Two modes: output_item.done for both messages, or text deltas only. Terminal output is full, empty, head-only or tail-only.

| Progress / terminal output | Turn result | Preserved messages | Provider usage in usage_summary |
|---|---|---|---|
| Done items / full | success | both |123 /45|
| Done items / empty | success | both via fallback |123 /45|
| Done items / head-only | explicit model protocol error | both preserved as completed progress |null|
| Done items / tail-only | explicit model protocol error | both preserved as completed progress |null|
| Deltas only / full | success | both |123 /45|
| Deltas only / empty | success | both via fallback |123 /45|
| Deltas only / head-only | success | FIRST_MESSAGE only |123 /45|
| Deltas only / tail-only | success | SECOND_MESSAGE only |123 /45|

For completed items, Core is **correctly fail-closed**: no false successful answer, no loss of the accepted completed-message progress. The fact that observed usage is subsequently erased is another example of the already reported validation/error usage-loss boundary, not counted again as a new issue. For deltas-only, previously presented text that is absent from a partial terminal is not retained in canonical history.

## Source boundary

- The adapter takes fallback_items only if `output.is_empty()`, then reconstructs deltas only if no item has any emittable text/tool call: [stream.rs lines128–149](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/openai/stream.rs#L128-L149). A nonempty proper subset skips both repair branches.
- Core requires accepted completed messages to be retained, with identical order/content: [progress.rs lines115–139](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model/progress.rs#L115-L139).

Do not relax Core's invariant. Either explicitly document that partial terminal payloads are rejected/not repaired, or define an adapter-local consistency/merge policy with identity/order checks and regression tests. No production patch is supplied because the desired behavior for this nonconforming provider output needs an explicit boundary.

## Verification

- `python3 -B run.py`: eight isolated real process sessions, eight local HTTP requests.
- `python3 -B verify.py`: confirms the eight captured outcomes and journal/usage evidence.
- The same native model-pack executable's158 tests were rerun successfully as part of the companion hook-usage-accounting audit. That is not a second distinct158-test run.
- No live LLM, keys, UI, production edits or remote writes. `analysis.json` is the compact captured-result summary; requests, journals, app-server events, synthetic configs, stderr and binary hashes are retained.
