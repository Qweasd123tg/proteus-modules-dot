# Candidate MDC-1: inherited Model::complete loses a typed canonical error terminal

Status: **independent source review PASS, narrow P3 public Rust API consistency candidate**. Bounded published-report dedup is described below. This is not a normal app-server or shipped-workflow regression claim. No Rust/project code/tests/scripts/fixtures/providers/GUI executed; no production modification. The only execution was a separate author-written abstract Python fold, not Proteus.

Baseline: upstream Core `89997df995df7c39b713e16aba216ecb19c8f497` plus delivery PR87–89; resulting tree `00a3c04a70d7927d1688ea155142025f596a2874`. Revalidate after upstream changes.

## Contract and exact source consequence

`ModelFailure` exists to preserve a provider-neutral actionable kind, message and completed assistant messages (`proteus-contracts/src/model_standard/failure.rs:5–32`). `Retryable` may include `retry_delay_ms`; `ModelFailure::from_error` preserves a downcastable typed error, otherwise synthesizes Other with no completed messages (`:49–57`). The process/canonical contract explicitly carries this whole DTO in error terminals (`docs/architecture/process-module-architecture.md:975–1002`).

The public trait's default helper in `proteus-contracts/src/contracts/model.rs:49–56` loops over stream events, applying `event?`, but only recognizes `ModelStreamEvent::Response`. A valid `Ok(ModelStreamEvent::Error { failure })` is discarded. If that failed stream then ends normally, the helper returns only `model stream ended without a complete response`.

Thus a consumer of the inherited helper cannot recover the original message, failure kind, retry advice or completed messages. `ModelFailure::from_error` on this result yields Other with empty progress. This does not require malformed events, races, cancellation or a provider-specific mapping error: the input already contains the correct typed failure.

`ModelService::complete` (`core/model_service.rs:78–93`) and `BoundModel::complete` (`core/bound_model.rs:393–403`) explicitly handle that same canonical Error event by returning the original typed failure. These implementations of the same Model trait provide a precise local consistency control.

## Reachability and scope

- `ProcessModel` implements `Model::stream` but does not override complete. Its terminal mapping at `process_adapters/model.rs:300–303` yields a canonical Error for `ProcessModelTerminal::StreamError`, while RequestError becomes an outer typed stream Err.
- `ModuleCatalog::build_model_adapter` is public and returns the raw `Arc<dyn Model>` (`core/module_catalog.rs:275–289`). The model factory constructs ProcessModel directly (`module_catalog/components.rs:63–77`); it does not add ModelService. A direct Rust consumer of that public catalog API can therefore reach the inherited helper with a process StreamError. A custom stream-only Model implementation can reach it without any process at all.
- Ordinary recorded workflow model calls use BoundModel; it overrides complete correctly. ModelService also overrides it correctly. No current product HTTP/ACP/GUI path using the faulty inherited helper was established, and no automatic-retry failure or persisted-history loss is claimed.
- The direct Rust surface is enough for this limited API consistency candidate, but not evidence of occurrence in stock workflows. The public contracts crate explicitly serves shared host/worker Rust contracts; this is not a proposed new native module integration path.

## Minimal regression plan, NOT RUN

Create a test-only in-memory `Model` implementing id, capabilities and stream, but leaving complete inherited. The stream returns one `Ok(ModelStreamEvent::Error { failure })`, then EOF. Use `failure = ModelFailure::new(Retryable { retry_delay_ms: Some(1500) }, "transient provider condition").with_completed_messages([valid assistant item])`.

Call the adapter's inherited `.complete(request).await`. A preservation assertion using `downcast_ref::<ModelFailure>()` or `ModelFailure::from_error` should equal the full supplied failure. Current source instead returns the generic EOF error and loses the typed fields.

Controls:
1. Successful Response returns the response.
2. A true EOF with only nonterminal events still returns a missing-terminal error.
3. An outer `Err(anyhow::Error::new(failure))` already preserves the failure via `event?`.
4. The same canonical Error through ModelService returns the original typed failure.
5. An optional MessageCompleted before the canonical Error does not repair the default helper. Use the completed_messages already supplied by the failure; do not invent delta reconstruction.

A real process-backed StreamError probe would add integration evidence, but was not run. Do not use invalid Error-then-Response sequences to inflate the impact.

## Existing tests and practical DRY fix

`core/model_service.rs::stream_error_propagates_as_anyhow` checks the correct wrapper, not the ScriptedAdapter's inherited helper. Its adapter only implements stream, so its shape is suitable for a small future direct-helper regression. `model_standard/failure.rs` tests typed preservation through anyhow context/wire validation, not stream draining. These are bounded inspected-test observations, not a repository-wide claim that no test exists.

Smallest correction: match both Response and Error in the trait default and return `Err(failure.into())` for Error. To prevent this already-visible divergence from recurring, consider one small pure terminal-drain helper used after each implementation obtains its own stream, or remove redundant overrides once the shared default has identical documented behavior. Preserve request shaping, response validation, bound event/journal ownership and each wrapper's stream construction. Do not implement the fix by bypassing BoundModel.stream or by silently adding ModelService preparation to raw adapter calls. Review the EOF message choice and existing tests deliberately; do not accidentally change error classification while deduplicating code.

## Evidence and dedup

Independent source review was read and 12 source SHA-256 entries were verified. Raw review/model artifacts are not included in this documentation package. The abstract finite-event model illustrates two failing projections and three controls; it imports no project code, cannot establish Rust compilation/process compatibility, and is not runtime reproduction.

Targeted duplicate checks: extracted prior audit DOCX text searched for Model::complete/default-complete/generic EOF and typed failure references; complete published `round3-framing/REPORT.md`, `round3-models/REPORT.md`, `model-context/REPORT.md` were read. The closest existing model-context finding concerns native Anthropic creating Other before the canonical boundary. Here a correctly typed canonical Error is erased later by a different, lower-level default Rust helper; normal wrapped provider/workflow execution is explicitly excluded. The earlier ACP final fallback and workflow stream-lineage reports have different cause and consumer. No exhaustive all-report dedup or claim of absolute novelty.

Source tree remained clean. Independent reviewer confirmed the exact branch, inherited ProcessModel path, wrapper controls and narrow scope. No production patch is included.

## Pinned source anchors

Key production files were not changed by delivery PR87–89.

- [crates/proteus-contracts/src/contracts/model.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/contracts/model.rs#L49-L56)
- [crates/proteus-contracts/src/model_standard/failure.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-contracts/src/model_standard/failure.rs#L49-L57)
- [crates/proteus-core/src/core/model_service.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/model_service.rs#L78-L95)
- [crates/proteus-core/src/core/bound_model.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_model.rs#L393-L403)
