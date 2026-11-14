# Workflow JSON codec: measured source-only simplification

## Decision

**A small practical refactor candidate, not a new defect finding.** Four WorkflowModule wrappers share typed input decoding and output encoding. All four explicit workflow invocations remain at their existing call sites; no callback framework, trait redesign, macro or shared execution loop is introduced.

Only isolated candidate/evidence files were written. Upstream production was not changed. This repository publishes proposal artifacts only. Independent source review found no semantic blocker. Compilation, formatting, tests and runtime remain unverified.

## Base and PR106

- Fresh Modules main: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Fresh Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules dependency pin remains `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- The inspected ProcessModuleError conversion and WorkflowFailure contract files are text-identical at that pin and Core main. This is a two-file check, not a fresh full compatibility certification.
- PR106 is a published sampling-lifecycle **candidate**, not deployed production. Its published patch was fetched and byte-checked against the preceding local candidate.
- This patch changes only `workflow/coding-workflow/src/workflows.rs`; PR106 changes different source files.

## Measured deletion

| Measure | Before | After |
|---|---:|---:|
| workflows.rs raw lines | 113 | 83 |
| serde input-decode sites | 4 | 1 |
| serde output-encode sites | 4 | 1 |

Net **30 raw lines / 27 nonblank lines removed**, including both helpers and the additional type import. Unified diff: 51 removed / 21 added. No deletion is hidden in another file. The measured scope is this one source file, not the entire crate.

The main gain is removing four copies of JSON boundary/error boilerplate without hiding which algorithm executes. Runtime speed, memory, code size and defect-rate improvements are not measured or claimed. This is a modest local simplification, not a major architectural redesign.

## Preserved responsibilities

Each wrapper visibly does:
1. `decode_input(&input_json)?`;
2. its existing `run_single_loop`, `run_codex_loop`, `run_plan_execute_review` or `run_project_check` call, with the same parameters;
3. `encode_output(&output)`.

Only the codec is shared. Module IDs, max_tool_rounds, workflow sequencing, host access, sampling, checkpointing, tool execution, result/history ownership and settlement are unchanged by this candidate.

## Source-reviewed equivalence

| Boundary | Evidence |
|---|---|
| Invalid input | Same serde decoder and WorkflowModuleInput type, same error.to_string → WorkflowFailure::new mapping. Decode still short-circuits before any run_* invocation. |
| Successful output | Same WorkflowModuleOutput value serialized by the same serde serializer. Helper borrows output exactly as the original code did. |
| Three WorkflowFailure-returning algorithms | `?` propagates the same WorkflowFailure value instead of the old Err(error) arm; history/model_failure are not reconstructed from text. |
| ProjectCheck ProcessModuleError | `?` uses the existing From conversion, equivalent to the previous error.into(). That conversion preserves message/model_failure and has history:None, as before. |
| JSON encode error | Same WorkflowFailure::new(error.to_string()) mapping; not confused with an algorithm failure. |
| String wrapping | Removed String::from(String) identity wrapping in three success arms; no runtime allocation gain claimed. |
| Algorithm invocation | One explicit call per successfully decoded invocation, with unchanged self.max_tool_rounds/CODEX_LOOP_MODULE_ID and host argument. |

No existing bug, including prior typed-failure/history findings, is claimed fixed.

## Checks actually completed

- Nine source Git blobs matched their remote identities.
- `git apply --check` succeeded against the exact isolated Modules baseline.
- In two separate isolated source copies, applied **PR106 then this patch** and **this patch then PR106**. Both orders succeeded and all five resulting Rust files were byte-identical.
- The fetched published PR106 patch SHA256 is `d60add66d35fe7e8dd322cc38d794ca723ae03f649b4cf9d6ec5845b0bc66b5c`.
- Independent source review separately confirmed the 113 → 83 raw-line count, nonblank reduction, codec call counts and error propagation.

These are **source/text checks**, not toolchain execution, tests or behavioral proof. Patch composition does not establish compilation of either candidate.

## Gates before application to production

1. Rebase/check against the intended target including other functional patches. Keep Core dependency pins unchanged.
2. Run formatting, compilation and the coding-workflow package tests once the toolchain is available and execution is authorized.
3. Add/verify boundary cases for all four wrappers: malformed JSON before host activity; successful output JSON equality; algorithm failure preserving structured WorkflowFailure; ProjectCheck typed ProcessModuleError conversion.
4. Retain existing completed-effect failure-history regression coverage. Verify typed model_failure as well as human-readable error text.
5. Do not expand this into a generic host-RPC framework solely to remove more lines.

## Evidence and limits

[Candidate patch](workflow-json-codec.patch), [measurements](MEASUREMENTS.json), [independent review](JSON-CODEC-REVIEW.md), [source identities](SOURCES.json), [read verification](READ-VERIFICATION.json), [Core pin comparison](PIN-COMPARISON.json), [PR106 composition check](COMPOSITION-CHECK.json).

Local before/after evidence and disposable composition copies are not included in this publication. Python was used only for text transformation, counting and hashes. Git was used only for candidate patch applicability/application within those isolated copies.

No project code, project validator, tests, fixtures, compiler, rustfmt/clippy, provider/runtime or dependency installer was run. No security/flagged area was investigated. Merging this evidence package does not apply the candidate to upstream production.
