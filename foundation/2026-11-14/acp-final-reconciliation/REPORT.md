# DS11 candidate: earlier assistant commentary suppresses an unstreamed canonical ACP final

Status: independent source review PASS, P3 custom-workflow interoperability candidate. Runtime regression not run; independent review caveats are incorporated. No Rust/project code, module fixture, tests, ACP process, GUI or provider was executed. Only a separate author-created abstract Python projection model was run; it is not runtime evidence and is not included. No production changes.

Exact base: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89; tree `00a3c04a70d7927d1688ea155142025f596a2874`. Later upstream changes require revalidation.

## Exact scope

The case is **not** that every `AgentOutput.text` different from a streamed message must be appended. An output may deliberately be a status summary: the existing `runtime/tests.rs:183–202` ModelCallingWorkflow returns `output.text = "done"` with distinct model `response.messages`. Blind string comparison would introduce new duplicates/status text.

Instead, this witness returns an actual distinct final assistant message F in `WorkflowOutput.new_messages`, with `output.text = F.text`, after publishing earlier commentary C. F itself has never been streamed. Both C and F have ordinary unique canonical message/part IDs. Their contents are immutable; there is no malformed stream, lag, cancellation, private peer event, model error or output mutation.

This is a configurable custom `workflow/v20` producer, not a demonstration against a shipped default workflow. ACP sessions use the selected configured workflow. The real ACP endpoint was not run, so reachability is a traced source path, not an observed E2E result.

## Contract and source chain

1. `proteus-contracts/src/contracts/workflow.rs:322–357` accepts separate `output` and persistent `new_messages`; it does not require every persistent assistant message to have emitted `AssistantMessageCompleted`. The existing **model-free** `tests/fixtures/finalization_workflow.py` returns the same final text in output and new_messages without emitting a final message event. This fixture was read only, not run.
2. A root workflow may emit optional progress through `host.events.emit` (`contracts/workflow.rs:38`, `process_adapters/workflow.rs:229–240`, `core/workflow_host.rs:293–295`, `AgentWorkflowContext::emit` at `contracts/workflow.rs:296–305`). The host supplies the current root event context. No requirement forces an extra final-message event after an earlier commentary event.
3. The event contract itself distinguishes the units: `domain/events.rs:254–260` describes `AssistantMessageCompleted` as a single assistant item, **not the whole turn's terminal output**. Thus seeing C completed does not establish that final F was delivered.
4. With inactive hooks, `core/reviewed_workflow.rs:51–53` returns the workflow directly. `runtime/history.rs:18–37,63–83,110–117` accepts the nonempty assistant suffix [C,F]. `runtime/turn.rs:458–475` commits it and returns the output; it does not synthesize an AssistantMessageCompleted event for F. Success settlement retains that output at `turn.rs:204–209`.
5. `app_server.rs:158–173` publishes the terminal `AppServerEvent::TurnOutput` with F before returning the same output. ACP's `Prompt::event` processes runtime envelopes and supported question/permission events but not `TurnOutput`; the default branch discards it. A workflow `TurnFinished {output:F}` event would likewise be ignored by `Projection::event`'s default branch. This witness may include that ordinary terminal event; its presence does not rescue F.
6. ACP `Projection::event` (`acp/projection.rs:60–71`) stores C in `texts`; `fallback_output` (`:121–126`) suppresses **all** fallback text whenever any stored item is nonempty. `Prompt::drive` (`acp/prompt.rs:77–109`) drains terminal events, calls this fallback with F, then returns `EndTurn`. Therefore the client receives C but not F, even though canonical history and the successful output contain F.

`docs/guides/runtime-and-events.md:146–147,192–198` describes ACP text updates, completed-prefix dedup, and canonical persistence. It does not require clients to reconstruct missing finals from app-server snapshots; ACP explicitly does not blindly replay those snapshots. The whole-turn fallback's predicate confuses per-item text activity with delivery of the accepted final answer.

## Minimal source-derived producer and regression plan, NOT RUN

Use the existing model-free finalization fixture's `workflow/v20` success shape in a test-only custom module. Give the run no active hooks, model or tools. On one root run:

1. Make C = Assistant/Commentary text `Preparing the result.` and F = Assistant/FinalAnswer text `The final result is 42.` with distinct fresh message and part IDs.
2. Emit `AssistantMessageCompleted { message_id:C.id, phase:commentary, text:C.text }` through `host.events.emit` and await its ACK. Optionally emit ordinary `TurnFinished {output:F}` as well.
3. Return success `WorkflowOutput { output:{text:F.text, metadata:null}, new_messages:[C,F], history_replacement:null, compactions:[] }`. There are no tool bindings, user suffixes, compactions, checkpoints or special provenance claims.
4. Drive real `session/new` and `session/prompt` using the configured module. Check the response is `end_turn`, canonical history retains C,F, successful settlement output is F, but the collected ACP agent-message chunks contain only C.

Future positive controls: no commentary event (fallback shows F); explicit F completion event (F shown once); Unicode prefix/completion dedup; peer events ignored; a distinct status-only AgentOutput with no missing canonical final (do not blindly append it). Run these only when the project toolchain/fixture execution is authorized and available. Nothing here asserts these Rust/ACP tests already ran.

## Practical improvement / DRY

Make accepted assistant completion identity, rather than "some text was seen", the single authority for terminal reconciliation. Reuse canonical message IDs and the existing prefix-aware completed-item projector. One option is a host-owned accepted-completion summary carrying the missing canonical assistant items; another is an explicit completion contract that all producers and consumers consistently implement. Preserve ordering before the prompt response and reject attempts to rewrite an already-published prefix.

Do not fix this by blindly appending every differing `AgentOutput.text`, by replaying an entire SessionSnapshot, by inferring finality from nonempty text, or by switching to module-name-specific exceptions. Output text has no message ID today, so plain string equality cannot reliably identify the final item. No new behavior slot is needed. The change should define the smallest common terminal presentation boundary and remove the heuristic in one place.

## Dedup / evidence limits

The published `acp-cli/REPORT.md` already lists ACP fallback with an unusual workflow as an **unpromoted hypothesis because no violating producer had been established**. This report develops that exact earlier hypothesis with a contract-valid model-free producer and full source trace. It must not be presented as an entirely unknown topic or a newly measured runtime failure. Independent review accepted this bounded source-only reachability, not a runtime demonstration.

Read all local ACP projection/prompt/unit tests and the full ACP integration test source plus fixture; read the workflow output/event DTOs and exact host/terminal paths above. Existing ACP tests cover duplicate suppression for the same streamed completion and the ordinary single-loop output; they do not cover [published C, unstreamed persistent F]. This is a bounded inspected-test claim, not a repository-wide claim.

The separate abstract projection model (not included here) is an abstract model of this acceptance/suppression decision, not an import or execution of Proteus. It cannot establish process compatibility, real wire encoding, runtime scheduling or frequency. Canonical history is not lost; it remains available to other Proteus clients. No provider/billing/security effect is claimed.

## Additional producer provenance

`app_server/runs/tests.rs:12–22,25–56` configures the existing finalization fixture with no providers and expects ordinary AgentAppServer success. `acp/mod.rs:215–223` launches the selected configuration through the same AgentAppServer boundary. These test/source definitions support the model-free producer route but were not executed in this audit. The added C-emitting variant remains a proposed regression fixture, not an existing shipped implementation.

## Pinned source anchors

Paths below are relative to `crates/proteus-core/src/`; key production files were not changed by delivery PR87–89.

- [app_server/acp/projection.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/acp/projection.rs#L121-L126)
- [app_server/acp/prompt.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/acp/prompt.rs#L77-L109)
- [core/runtime/turn.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/turn.rs#L458-L475)
