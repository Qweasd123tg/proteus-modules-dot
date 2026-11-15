# Independent exact source review: Pi terminal outcome on PR126

## Verdict

No source-level blocker found for the supplied bounded candidate. The conservative reducer implements the refined contract, rather than treating any historical error as permanent failure or agent_end as session settlement. Accepted for the proposed narrowly scoped synthetic checks, not asserted to compile/run/pass yet. I executed no project imports, Python tests, Pi/native CLI, models or other project targets.

Baseline is Core bcbda4435534a296c707a1daa250813d692f68e1 plus exact PR126. This patch is not represented as directly applicable to unmodified Core. Thirteen exact Git blobs and inert apply equality are coordinator evidence.

## Reducer and integration

agent_start begins pending activity and clears the terminal candidate. User/assistant message activity and JSON message_update clear it again. Only a subsequent agent_end with a prior start, literal willRetry is False and a list of messages supplies the last assistant stop. agent_end itself remains pending. agent_settled records the candidate and its explicit aborted value, then clears state. A subsequent trailing start/message prevents whole-outcome success; extra/missing settlements fail exact-count validation. A continuation failing before its own agent_end cannot inherit an earlier stop. An agent_end without a corresponding start also cannot create clean evidence.

successful_pi_generations requires a positive exact int expected_turns (not bool), pending is False, exact settlement count, every stop_reason=='stop' and aborted is False. Unknown, absent, future, toolUse and deferred are nonclean for this evaluator, not universally erroneous Pi outcomes. This is not a generic arbitrary-input validator; unexpected top-level/field types may still raise rather than return a classified unknown.

Adapter usage collection/sum formulas and model/tool counters are untouched. Historical error/aborted messages remain in errors. Newly appended terminal-length diagnostics are limited to committed settlements; recovered intermediate length remains in observed_stop_reasons without a terminal-length error. Runner changes only Pi's complete predicate; existing exit/timeout/model/provider/reasoning/continuity/error guards remain. Other arms retain previous completion policy.

Usage fallback reuses the same event reducer from stdout instead of a second terminal policy. Stored pipeline_ok fast path is unchanged, deliberately not a historical regrade. A failed old artifact without complete agent_settled evidence becomes unknown. The usage predicate denotes clean final generation, not complete billing or success of postprocessing: a threshold-compaction failure after a final stop can leave generation complete while the runner still rejects nonzero exit. F4 missing usage rows is untouched.

README accurately limits the result to pinned Pi/harness behavior and describes the compatibility cost. No historical results or scores are rewritten by this patch. Generic taxonomy code is unchanged; terminal length is exposed through the existing length-limit diagnostic route rather than a new report taxonomy.

## Proposed controls and runtime scope

Nine methods cover recovered error, terminal length, recovered length, exact per-run settlements, missing/invalidated evidence, retained pipeline guards/postprocessing distinction, other-arm controls, and stored-success fast path. Source assertions are consistent with the reducer and unchanged metric sums. PR126's teardown fixture now includes authentic start/end/settled boundary shapes; its six tests remain a separate regression target.

The two proposed baseline controls are appropriate behavioral red controls: recovered-error first expects pipeline success where baseline rejects historical errors; terminal-length first expects failure where baseline accepts a settled error-free numeric run. Those assertions occur before access to new pi_outcome fields, so expected baseline failure is not merely missing helper/import/field. The test module does not import pi_terminal directly. Baseline preparation must still include all existing imported sibling modules and copy only the test file, not patched production, for that claim to hold.

Inspected imports/entry-point structure and exercised call paths: tests call adapters.metrics for Pi, runner.check_pipeline, reporting functions and temporary synthetic file fixtures. Dependencies are stdlib plus sibling harness modules. runner imports open_code_native but its CLI entry point is guarded; no test invokes its execution methods, runner main, adapters preparation, model APIs or native CLI. This is a source assessment of the proposed target, not network-capture evidence or approval for other targets. No runtime results are asserted here.

Limits: these fixtures are synthetic rather than a real pinned Pi run; not every malformed event, deferred-tool integration or exception path is covered. The continuity guard subcase combines wrong expected count and false continuity, so does not independently isolate continuity, although its production guard is unchanged. No broad F1/F2 closure outside native Pi is established.

## Own SHA256

- pi-terminal-on-pr126.patch: b2b457e7dd2cfb17e1489ef97728080c09b306d9dedd0456f5c2b65b8114a2ee
- pi_terminal.py: ce2428f92568b2172076f13d0e5d56c3ffb30c73e498495901b18e167f6ce180
- pi_terminal_test.py: 112c533b5f4cc562729bc1383dfc8eb00bccd4532c95827ac5709312a2bdc607
- adapters.py: 6a405af6f956dc9ee3f815784c296c7dbac002a277816aa2665a857b29470993
- runner.py: 4febb02b8c4ec2e94fe24144762edbe68f09758b1115ffc4a5c1d3667801d78f
- usage_report.py: 270db9932981e8ee9f220dc0807237550abccc59cb4533067a3897261194abba
- usage_report_test.py: 58a1836d71c15ead6c7a8b2fe1eb479782dea7885bd20567de4b62451f3f45cc

No production integration/publication or unrelated subsystem review performed.

## Added ordinary tool-turn control

Read the added test_tool_use_can_reach_clean_answer_in_one_low_level_run fixture. It uses one agent_start, toolUse assistant completion, a toolResult, then a second assistant completion and one final agent_end containing the ordered messages, followed by settlement. It correctly exercises the last-assistant selection without treating toolResult as a new session or toolUse as final failure. Expected two model requests and one tool call match the unchanged adapter counters. The fixture is a reduced synthetic protocol projection, not a full recorded Pi trace or actual tool execution.

Own final patch hash b2b457e7… and test hash 112c533b… are updated above; production bytes are unchanged per coordinator. Nine new tests plus six prior PR126 tests remain NOT RUN at this source-review stage. Earlier inert apply equality belongs to the prior revision; final --check is coordinator evidence, final applied-byte verification is still pending runtime-copy preparation. No source-level blocker found; no tests rerun by this reviewer.
