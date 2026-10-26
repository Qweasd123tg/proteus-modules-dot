# Existing producer and the actual missing consumer

Source inspection only, 2026-10-26. This narrows the proposals in ecosystem Round5/6; those historical reports remain unchanged.

## Do not duplicate collection

Core already has a compact `SessionUsageSnapshot`, not merely the eval-report aggregate. Its rows contain exchange ID, turn, requested model, Direct/Auxiliary, request/finish timestamps, status, optional provider-normalized usage, prompt/tool counts and selected reasoning/output limits. `Option<TokenUsage>` explicitly distinguishes absence from zero. [Schema](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-contracts/src/domain/usage.rs#L10-L46).

Real producer: `UsageProjection::apply` copies request fields, joins response by exchange ID, copies usage only from a successful canonical response, and assigns Error on a model error. Turn settlement only changes still-pending rows. It does not retain OperationOwner, failure kind, provider metadata or retry lineage. [Projection](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_journal/usage.rs#L18-L82).

The producer has real consumers: stdio `usage_summary` serializes the selected server's snapshot; the existing `/usage` command renders it; the HTTP usage path selects a session and either accesses its live server or uses SessionStore. The proposed example consumes an operator-selected **payload export**, not a new hidden-file tool. [Stdio](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/stdio.rs#L176-L181), [command](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/commands.rs#L117-L132), [HTTP consumer](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/http/sessions.rs#L200-L213).

Warm usage projection is applied after append sync and state-validation commit. Cold usage falls back to validated journal projection, with an existing Unix read-metadata cache path. This establishes source-level dataflow, not a new test of filesystem durability/cache correctness. Arbitrary JSON of the same shape is not authenticated by a summarizer. [Append](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_journal/storage/append.rs#L121-L143), [read path](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_store/usage.rs#L4-L29).

## Limits that must survive presentation

- Request-recorded occurs before provider start and before cancellation/deadline selection finishes. Exchange count is not provider-attempt count. [BoundModel](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_model.rs#L263-L309).
- Requested model is copied from canonical request, not independently confirmed serving-model identity.
- An Error row omits failure kind and any incomplete stream usage; do not interpret error text or turn status as exact provider cause.
- Canceled/Timeout rows can have no finished timestamp because those statuses arise from turn settlement of pending exchanges. Do not require a response timestamp for them or fabricate latency.
- The revision tracks relevant usage events, not every journal record or conversation mutation. Re-reading the same snapshot must not add its totals again.
- Optional cache/reasoning counts are independently missing; they are not extra tokens to add to input+output.
- `OperationOwner` exists in ModelRequestRecorded but is deliberately absent from the compact usage row. Owner-aware export needs a separately reviewed app-owned consumer of validated journal facts. [Journal request DTO](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_journal/types.rs#L58-L86).
- Existing eval-report sums known usage and byte/4 estimated request sizes; that does not make the new grouping a price estimator. [Eval aggregate](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/eval_report.rs#L111-L129).

## Pin compatibility evidence

`source-pins.json` covers 22 selectively read files. All seven selected contracts files and the actual UsageProjection implementation are byte-identical between published SDK/Core `3f36a003b4f3fde2242fc80f7aedac00dd127d1d` and current Core `1fc3ef223d10322815dd9290a50d045bc95402bb`. Five selected Core files differ (one new read-model file is absent at old pin); no full-Core compatibility claim. Use direct pinned `proteus-contracts` for the pure app-side consumer; no Core dependency or SDK module runtime needed.

Upstream usage tests were read as examples of intended producer behavior, **not run**. The new fixture corpus will use actual typed schema shapes and isolate missingness/grouping errors; it will not be represented as actual AppServer/Core integration.
