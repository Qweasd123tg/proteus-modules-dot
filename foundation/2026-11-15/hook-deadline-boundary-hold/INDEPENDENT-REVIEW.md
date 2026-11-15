# Independent source/design review: BeforeModel and model deadline

## Verdict

HOLD choosing a patch until the phase boundary is explicit. The observed implementation is a hybrid, but inspected docs/tests do not unambiguously authorize either excluding BeforeModel from the model budget or interrupting it under that budget. This is a bounded review of a known family, not a new reproduced incident. No Rust/compiler/tests/project scripts/application runtime were executed; no candidate or production edit was made.

## Observed behavior

Core main bcbda4435534a296c707a1daa250813d692f68e1, bound_model.rs:
- stream creates deadline before stream_with_deadline.
- apply_before_model is awaited without a local deadline select. It includes preparation/binding, optional conversation read and hook chain, followed by preparation/binding again.
- model_request_recorded is awaited after hooks and before the deadline select; exchange_id is allocated only after successful preparation.
- Provider start, bound recording stream, and presentation then receive the same absolute deadline. Auxiliary BoundModel calls also start their own deadline; they skip the recursive BeforeModel chain, not all preparation.

Consequently successful long preparation/hook work consumes the later provider budget while not being interrupted by that model timer. An already expired deadline wins the biased start select after request recording, before provider start is polled. An earlier hook failure returns first. This is source reasoning, not elapsed-time measurement; outer workflow/process cancellation and hook protocol limits can still stop work. The model timer is not currently a strict bound on every awaited preparation/recording/settlement operation.

## Contract evidence does not select the missing boundary

runtime-and-events.md describes one model deadline for request startup and streaming, including retry/backoff. configuration.md distinguishes the turn budget, separate model calls, and optional hook export timeout. hook-tool-operations.md permits BeforeModel to perform auxiliary model/tool work and assigns inherited parent cancellation/budget. None of those inspected passages expressly says whether the enclosing model-call timer starts before or after BeforeModel.

The nine deadline controls exercise pending provider start, delayed/continuous stream, disabled timeout, stalled sinks, retained terminal response, provider drop before blocked error recording, and cancellation. They protect important existing semantics but do not test a slow BeforeModel hook against the enclosing model timer. Inspected execution hook controls establish ordered accepted transformations and failure behavior, not this duration boundary. Their absence is not proof of intended exclusion.

## Why neither one-line change is semantically neutral

Moving deadline creation after preparation gives the provider phase a fresh budget. That is coherent and potentially small, but deliberately lets hook work plus provider work exceed the former elapsed model budget. Workflow/hook limits remain separate; zero workflow timeout does not turn that into an unchanged total bound. All uses, including presentation, must share the newly selected deadline, not accidentally retain an earlier one or reset per retry. The location relative to request recording also needs a stated meaning.

Wrapping apply_before_model in a timeout/select instead enforces a broader operation policy. Simply dropping it can discard accepted HookTrace steps held locally before hook_recorded, while auxiliary model/tool work may already have effects and separate records. RuntimeHookChain currently derives child cancellation from operation/turn scope, not the enclosing model deadline. Its cancellation path explicitly cancels the handler token and gives bounded settlement time before recording a failed trace. A timeout must not bypass that machinery or cancel unrelated work via a shared turn token.

The existing operation scope and child-token mechanisms offer building blocks; no new public framework/DTO is proved necessary. But an invocation-local timeout must deliberately coordinate child cancellation, accepted trace persistence, auxiliary effects, failure identity, and settlement. Because the model exchange does not yet exist before successful hooks, 'record the same exchange error' cannot simply be assumed for preparation timeout. Existing tests that drop providers before blocked terminal recording also warn against holding active work alive while awaiting slow settlement. No claim that current cancellation machinery alone already solves every new timeout path is made.

## Required choice and later bounded controls

Choose and document either provider-phase budget or encompassing preparation budget, with recording/settlement limits explicit. Then a focused candidate can be assessed without architecture for its own sake. Suggested source tests must distinguish:
- slow successful BeforeModel versus provider start budget;
- hook failure versus outer timeout and external cancellation;
- auxiliary calls having their own deadlines without recursive BeforeModel;
- accepted earlier hook steps followed by a timed-out later hook;
- child work/effects and replay trace settlement;
- unchanged total stream/retry deadline and stalled sink/provider-drop controls.

These are not implemented or passing tests. A simple deadline move cannot presently be certified as contract-preserving solely from the inspected prose; a simple timeout drop is insufficiently justified. HOLD is a semantic-selection result, not an assertion that a narrow fix is impossible.

## Identity and scope

Coordinator catalog contains 14 exact Core source files. Own SHA256 checks:
- bound_model.rs: acc9f9484a245cfda03574e862279dbd6c085fd802b59b03ece2130c5dc88361
- bound_model/hooks.rs: b310fd0219f005e6223bec55fd0503474ed2a06833fd7e509401d00b90bc4e6f
- execution_hooks.rs: cd8cbdf851c7e6673e4c664649afb6f8e0a23ae38bebfc4515230218817de59c
- model_call_scope.rs: 64a77e001a21bbaea5bb2bdec063ce5bcef50eb8c750ff7897df3238b0025b07
- bound_model_tests/deadline.rs: 36d97f1027f792611d586f7e09e1d0b2ccc06ac25c24ebfcbbd006e2198f1e11

Reviewed only timing, phase ownership, cancellation propagation, and recording consequences. No security/authority review, publication, or runtime reproduction.

## Final report and boundary granularity addendum

Read the original pre-publication REPORT.md in full and independently verified SHA256 9255dbd3142c5193df494f3c2df5b63f0b2afa749d7afbf534f461ea7ef8127c. No blocking overclaim found. Its phase table correctly distinguishes clock charging, deadline observation, and recording/settlement rather than claiming a hard wall-clock bound. In particular, moving creation immediately after apply_before_model still charges model_request_recorded while awaiting it outside select; that is not strictly provider-only. The initial review's provider-phase alternative is conditional on explicitly selecting this recording boundary.

Read ExecutionScope::child_cancellation_scope: it preserves execution_id and derives a child token. Together with existing with_operation_scope it provides a local-cancellation building block, not automatic proof of trace/effect settlement. Re-read the terminal_response_is_not_replaced_when_final_sink_stalls control and relevant presentation path: the report properly preserves an already accepted/recorded response instead of endorsing blanket timeout/drop around final delivery. This must remain distinct from a hard limit on durable terminal recording awaits.

The catalog now contains 18 exact source blobs according to coordinator verification, superseding earlier 14/17 counts. Final report and proposed validation remain HOLD with no patch and no new implemented/executed tests. Verdict unchanged; this addendum performed source/text reads only.

Publication note: the original report hash above identifies the pre-publication report. README.md has presentation-only edits for repository links, source catalog, and publication status; the HOLD verdict and technical scope are unchanged.
