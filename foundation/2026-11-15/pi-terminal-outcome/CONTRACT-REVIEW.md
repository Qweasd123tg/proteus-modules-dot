# Independent contract review: Pi terminal outcome, F1/F2

## Verdict

Proceed to a bounded candidate only with conservative event-state guards; do not implement the naive last-stop-since-settlement reducer. The pinned source supports replacing historical-error presence with session terminal evidence for this controlled harness. It does not support a universal Pi success classifier or equating agent_settled with success. No project code, Python imports/tests, Pi process or model calls were run in this pass.

## Proven boundary

At upstream b4afdddf44e059c67ccf5097e5317d913521b470, _startRun awaits agent.prompt, then may repeat agent.continue for retry, compaction and boundary continuation. _willRetryAfterAgentEnd checks retryable-error policy only. Therefore agent_end(willRetry=false) is not a final session-run boundary. JSON mode forwards agent_settled unchanged through toJsonEvent.

_emitAgentSettled occurs in the finally around the low-level run/continuation sequence. It carries aborted, not success, and may follow an exception. Preparation errors before that try do NOT emit agent_settled. Thus describe it as the settlement signal for a started run, not guaranteed exactly once for every attempted prompt. Extension-settled actions may schedule further prompts; exact expected-turn count is defensible only under the selected harness, not arbitrary extension behavior.

print-mode JSON does not apply text-mode's final assistant error/aborted/length exit-code check. Existing runner's returncode guard must remain, but returncode zero alone cannot classify JSON success. Existing historical errors remain useful diagnostics and should not be deleted when a later recovery succeeds.

## Minimal coherent reducer requirements

- Count session settlements, not low-level agent_end events. Require exact positive expected_turns (reject bool/non-integer/nonpositive when validating this parameter), and no trailing activity after the last settlement.
- Track final completed assistant evidence for the current low-level activity. Invalidate the prior terminal candidate at each new agent_start and at a new assistant message_start/update before its authoritative message_end. Merely resetting at agent_settled is insufficient: a prior stop followed by a new continuation that fails before its own message_end must not inherit success.
- Treat missing/null/non-boolean aborted as unknown, not False. Accept success only with aborted is False and an eligible final completed assistant stopReason == 'stop'. Missing/malformed event sequence or absent final message must fail closed as unknown/non-success, not silently borrow an earlier run's stop.
- Preserve ordered historical stops/errors separately from the terminal decision. A recovered intermediate length/error is not itself terminal task failure; final length is not success. A trailing run/start/assistant attempt without settlement stays incomplete, even if the previous expected settlement count was reached.
- A second low-level run inside one session run must not create a second expected-turn settlement. agent_end may optionally validate low-level completion, but cannot alone complete the session outcome.

agent_settled(false) plus last stop still is not a theorem that no exception occurred afterward. Runner returncode/timed_out/error/model/reasoning/continuity guards must remain. For usage-completion fallback after CLI failure, the result is a selected lifecycle-evidence policy, not proof of successful pipeline or complete accounting. Keep the existing universal pipeline_ok fast path only as explicit backward-compatibility policy; it intentionally trusts stored outcomes rather than retroactively regrading old artifacts.

## ToolUse and compatibility limits

The loop normally continues after tool calls. However upstream explicitly supports batch terminate hints and finishTurn action=end; these can legitimately end a run with a final toolUse message in broader integrations. A generic stop-only classifier would reject them. The harness command does specify --no-extensions and read,bash,edit,write. Before claiming those choices exclude all legitimate early termination, verify the pinned builtin tool result paths and default agent setup; the provided agent-loop/types/session sources demonstrate the extension points but do not alone prove every selected builtin never sets terminate. Conservative non-success for toolUse is acceptable for a clearly documented text-answer harness policy, not as a statement that Pi universally failed.

No new public protocol/framework is necessary: one small pure event reducer plus one policy predicate can own the definition consumed by adapter metrics, runner and usage fallback. Keep the result distinguishable as terminal success, terminal non-success, or incomplete/unknown, even if runner ultimately needs a boolean. Preserve existing metric fields and raw error history; add structured outcome rather than silently redefining diagnostic history as empty.

## Required scope and candidate controls

Do not alter usage summation or F4 missing native rows. Do not regenerate benchmark scores or reinterpret historical success tables. F2 classification should refer to final failed settlements, not every length occurrence; raw intermediate lengths remain diagnostic evidence.

Before runtime, source-check fixtures for recovered error/length→stop, final error/length/aborted, false/true/missing aborted, multiple expected prompts, extra settlements, low-level continuation within one prompt, incomplete trailing assistant, continuation-start without message_end, missing settlement, and valid ordinary tool-use→tool-result→stop. Also check legacy artifacts without agent_settled: fallback must not claim protocol support they lack. Proposed tests would not be passing evidence until separately authorized and executed.

## Independent identity checks

Own SHA256:
- agent-session.ts: dea73f4df16b15c927a4cb6b35ad7a3f9738232acb2d48473f0497f360fda6fe
- print-mode.ts: 327a903551b8c5ac08c9c6a9807e912fc63b55d5b405c619c86a7fb26169f4b1
- agent-loop.ts: 9d7589b5071ea3b8b3e3c624f9cfc09a976ebf7436024a58213837de4645167d

Read relevant JSON event projection, type termination hints, existing adapter Pi metrics and runner pipeline checks. No security/authority or unrelated execution mechanisms reviewed. Exact patch acceptance is deferred until a candidate exists; the naive reducer without invalidation/unknown handling is not approved.

## Refined design response

Coordinator proposes taking the candidate from the last assistant in the latest agent_end.messages, invalidating on new agent_start or relevant user/assistant activity, and committing only at agent_settled. This is a stronger bounded design: it requires low-level completion evidence instead of an arbitrary message_end, and prevents inheriting a prior stop when continuation fails before a new agent_end. Proceed to exact candidate review with the conservative guards above; no need for HOLD solely because the event reducer has state.

A terminal stop may precede threshold-compaction/postprocessing failure without another agent_start. Its settlement evidence must therefore mean final generation termination under this evaluator, not proof all session housekeeping succeeded. The runner retains independent process/status guards; usage fallback can recognize generation completion despite CLI teardown without calling the pipeline successful. Do not newly require every compaction notification to succeed without a separately chosen contract.

Using the same predicate for fallback intentionally makes old unsuccessful artifacts lacking agent_settled unknown. That compatibility cost should be documented, and old synthetic agent_end-only fixtures updated to authentic events. Preserving the stored pipeline_ok fast path is explicitly not a retroactive full F2 regrade. Exact implementation and tests remain unreviewed/unexecuted at this design stage.
