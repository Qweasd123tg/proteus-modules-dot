# Raw Function-argument compatibility revision — source only

This is a separate local revision of frozen `correction-memory` R17. The prior 24-file snapshot `0ba3a38573357c8e8658a410832ef43c2e464a72ce4c7f8dbaaa4e3cef7ea226` and source-readiness receipt remain unchanged. Neither revision has compiled or executed. This is a source-proven normal-wire refusal fix, not a runtime-reproduced defect or general security claim.

## Observed mismatch and bounded correction

Pinned SDK3f `tool.rs:86–104` parses a present `raw_arguments` string into `args`, validates the normalized call, and passes it to the module **while retaining the raw string**. R17's Function-and-raw-None check consequently rejects otherwise-valid normalized Function invocations such as INIT with `{}`/`"{}"`.

The revision still requires `ToolCallSurface::Function`. Before `Store::resolve` or any SQLite/evidence work it:

1. Limits a present raw UTF-8 string to `MAX_PROPOSAL + 256` = 33,024 bytes, including whitespace.
2. Strictly parses it using the existing duplicate-key rejecting, depth-24 JSON parser, including trailing-data rejection.
3. Requires the parsed JSON value to equal the supplied normalized `args`. A direct trait caller with inconsistent values is refused as `raw_arguments_normalization_mismatch`; the module does not silently choose another value after an embedding's authority decision.
4. Retains the existing normalized-argument bounds, tool-name allowlist, operator config, typed requests, store identity, evidence and transaction checks unchanged.

These are module-boundary limits **after SDK allocation/parsing**, not a claim that the SDK refuses oversized raw strings before allocation. Equality is equality of normalized `serde_json::Value`, not raw-text equality. Whitespace/key order can differ; duplicate keys are never accepted by this module when a raw string is still present. Existing typed integer/string/boolean request checks are unchanged.

## Actual host normalization order (pinned source trace only)

Core/SDK pin: `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`.

- Core `core/bound_tools.rs:274–282`: parseable raw becomes `args` before the requested-call recorder.
- Lines310–332: normalization repeats before observer/schema validation. Malformed raw fails validation instead of falling back to the competing parsed value.
- BeforeTool runs on that normalized call. `contracts/hook.rs:188–195` assigns a hook's replacement args, **clears raw**, and revalidates.
- `bound_tools.rs:347–399,454–469`: access policy and approval receive the same effective call; `bound_tools/invocation.rs:64–73` invokes it.
- `process_adapters/tool.rs:101–124` clones that call into the DTO. SDK `tool.rs:86–104` normalizes retained raw again before its schema and module invocation.

Thus, on this pinned path, input parsed-B/raw-A is A for schema/policy/approval/module; a hook replacement C clears raw and is C downstream. The wire test intentionally checks SDK canonical-A behavior rather than pretending to recover/reject the original B after normalization has discarded it. It does **not** execute Core policy or approval. Direct non-SDK embeddings remain responsible for normalizing before admission; this module rejects inconsistent direct-trait input instead of asserting every embedding is safe.

The pinned source locations above describe the inspected admission path, not a runtime result or general authorization proof.

## New authored tests (11; all unrun)

Seven direct-trait tests cover matching/null raw, direct mismatch before store resolution, root/nested duplicate keys with otherwise-matching normalized values, exact 33,024-byte limit and one over, malformed/trailing raw, targeted depth error, and unchanged Freeform refusal. Negative cases assert the intended diagnostic, zero verifier callbacks and no DB/sidecar creation.

Four own-binary wire tests cover valid raw INIT plus null-raw READ, canonical raw before SDK schema/module (including original parsed args that would fail INIT schema), duplicate keys whose last-wins SDK value is otherwise schema-valid, and malformed raw's SDK error. Unexpected callbacks are not serviced by these no-callback cases. Existing three wire and 55 other tests remain in the candidate, totaling **69 authored tests, all unrun**.

This does not add an authority grant, filesystem fallback, different schema/store policy, new dependency, migration, Core edit or arbitrary test runner. Same-instance backup rollback, evidence observation vs truth, postcommit response loss and all prior limits remain. It is not a substitute for the still-pending actual runtime gates.
