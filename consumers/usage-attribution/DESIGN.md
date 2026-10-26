# Usage attribution consumer — design, not runtime delivery

## Decision

Implement a small **app-side pure projection of the existing `SessionUsageSnapshot`**, not another journal, module host callback, cost gate, router or ToolModule. The real producer already exists: `AppServerHandle::usage_snapshot` → runtime → `SessionStore::usage_snapshot`; stdio `usage_summary`, HTTP usage and `/usage` command serialize that snapshot. The proposed example receives an operator-exported snapshot on stdin. It does not contact those endpoints, open a session directory, scan hidden files, start Core or grant an extension new authority.

The additional useful behavior is grouped accounting with explicit missingness. Existing usage rows already retain Direct/Auxiliary and each recorded exchange; the older eval-report aggregate loses that grouping. Do not replace either producer.

## Scope and pins

Core inspected at `1fc3ef223d10322815dd9290a50d045bc95402bb`; package contracts will be pinned to published SDK/Core `3f36a003b4f3fde2242fc80f7aedac00dd127d1d` only after exact selected-schema equality is recorded. No Core edits, network, provider calls, remote writes or local compilation. Author fixtures and send to reviewer before builder queue. Tests of upstream suites remain prohibited.

## Real producer semantics

- `ModelRequestRecorded` supplies exchange ID, origin, owner and canonical request. The usage projection copies requested model, origin, request sizes/settings, journal timestamps and turn ID, but **does not copy OperationOwner**.
- Request is recorded before the provider start select. Cancellation or deadline can finish it without a provider attempt. Thus `exchange_count` is not an HTTP-attempt count.
- Successful canonical response copies optional TokenUsage and finish reason. Error outcome maps to `Error` and does not preserve failure kind or partial stream usage in this snapshot.
- Turn settlement marks still-pending exchanges Canceled/Timeout; it does not set finished_at. Error caused by a canceled model call can remain `Error` if a response/error fact was already recorded. Preserve the producer's status; do not reinterpret text.
- Warm projection is updated after validated durable append. Cold reader uses the existing validated journal projection; read-model cache is another existing path. This source trace is not new runtime validation or independent authentication of an arbitrary JSON export.
- Snapshot revision is the last relevant usage projection sequence, not necessarily the latest journal record or conversation revision. Keep session ID + revision together and do not merge repeated snapshots additively.

## Available versus unavailable dimensions

| Dimension | V1 treatment |
|---|---|
| Direct/Auxiliary | Exact typed snapshot field; separate groups |
| Requested provider/model | Exact ModelRef; group by both strings |
| Recorded exchanges | Count unique exchange IDs; preserve unknown-usage IDs |
| Status | Preserve producer enum, not semantic success or cause inference |
| Provider-normalized usage | Sum observed canonical counters, known subset only |
| Missing usage | Separate count; missing is never zero |
| Cache/reasoning categories | Separate sums + reporting counts; overlapping categories are not added again to input/output total |
| OperationOwner | `not_exposed_by_snapshot`; never guessed from model name, prompt, tool count or origin |
| Provider HTTP attempts | `not_observed`; one exchange may start zero or several attempts |
| Retry/fallback relationship | `not_exposed_by_snapshot`; repeated model IDs are not proof of retry |
| Actual serving model | `not_exposed_by_snapshot`; requested model is not independently verified serving attribution |
| Currency cost | `not_computed`; no price table, conversion or billing claim |
| Estimated tokens | `not_computed`; do not mix eval's byte/4 heuristic into observed counters |
| Budget enforcement | `none`; report is read-only analysis |

The output is a summary, not a generic verification receipt. Deserializing an artifact does not prove that Core produced it or that its source journal is fresh/authentic. Producer provenance is caller-owned and stated in documentation, not accepted as a model-supplied `validated=true` claim.

## API and output

Library: `summarize(&SessionUsageSnapshot) -> Result<UsageAttributionReport, SummaryError>` using the actual pinned contracts type, not a handwritten lookalike input DTO.

Report: version; session_id; source_revision; source=`session_usage_snapshot`; `recorded_model_exchanges`; grouped rows keyed by origin/requested provider/requested model/status; each row has exchange_count, `usage_reported_exchanges`, `usage_missing_exchanges`, known input/output/total sums in u64, optional-category summaries (known_sum: Option<u64>, reported_exchanges, missing_exchanges), and missing-usage exchange IDs. Unknown dimension markers above are explicit constants. Empty snapshot is valid, with zero rows and no claim that an absent session has zero lifetime spend.

Use checked arithmetic, never TokenUsage's u32 saturating accumulator for multi-exchange totals. `known_sum=None` if no row reports a category; real reported zero remains `Some(0)`. Total known input+output counts each base category once; cache/reasoning fields are descriptive subsets, not extra charges.

Bounds before aggregation: at most 4096 requests; provider/model strings at most 512 UTF-8 bytes each, no truncation. ModelRef is preserved exactly, without provider aliasing or case folding. Duplicate exchange ID rejects the whole input. Host/source request order is not chronological-sorted or treated as retry lineage.

Producer-shape consistency checks (separate from journal/authenticity validation): Completed requires finished_at and finish_reason, permits optional usage; Error requires finished_at, no finish_reason/usage; Unfinished/Canceled/Timeout require no finished_at/finish_reason/usage. These reflect the pinned producer, not a universal future schema. Do not reject non-monotonic wall-clock timestamps or infer latency from them.

Example `usage-attribution-stdin` reads only stdin (bounded 8 MiB before parsing) and writes bounded JSON to stdout (2 MiB cap, no partial success). It accepts either a serialized snapshot or JSON null; null is an explicit unavailable result, not an empty snapshot. No filesystem arguments or fallback. SDK Serde parsing still owns duplicate-object-key behavior; do not advertise a stricter raw transport parser unless implemented/tested separately. Runtime usage_summary response-envelope selection remains the application's responsibility; the example consumes the payload, not arbitrary envelopes.

## Concrete use case

An operator exports the current session usage payload from the existing app API and pipes it into this example. The output says, for example: two Direct exchanges, one failed/missing usage; one Auxiliary exchange with known input/output tokens; owner, retry lineage, network attempt count and currency cost unknown. A second identical snapshot yields an identical report, not doubled spend. An actual zero-use response is distinct from a response without usage.

## Owner-aware extension: separate proposal only

If a UI genuinely needs owner detail, an app-owned exporter can obtain one already-authorized `JournalProjection` via existing SessionStore loading, then emit request/response facts joined by exchange ID, session/turn/execution identity and OperationOwner. That exporter must avoid prompts, tool args, failure messages, provider metadata and config snapshots. It must be tested against the actual Core reader. No such exporter or access grant is part of V1; no arbitrary caller-provided owner sidecar will be trusted as journal provenance.

## Causal authored tests required before any runtime claim

1. Actual SDK-shaped mixed Direct/Auxiliary fixture; exact grouped report and missing exchange IDs.
2. Known zero versus absent usage, isolated difference.
3. Same model repeated: separate exchange count, retry relationship remains unknown.
4. Same model string/different provider and same provider/model/different origin remain separate.
5. Explicit Error versus pending Canceled/Timeout, with producer-consistent timestamps; no inferred cause.
6. Optional cached/reasoning category absent versus zero; reporting denominator includes all exchanges in group.
7. Max u32 per-request counters sum accurately above u32; overlapping categories are not added to base total.
8. Duplicate exchange ID exact error; otherwise-valid input.
9. Each producer-shape contradiction separately, exact intended error.
10. Request cap exact/+1 and provider/model byte cap exact/+1, including multibyte strings.
11. Input permutation keeps group sums; source revision/session preserved; repeated invocation never accumulates.
12. Empty snapshot versus unavailable/null; no session lifetime zero claim.
13. Executable stdin positive payload and negative malformed/over-cap payload, exact exit/output; no files/network.

Predesign was independently cleared at 01:12 UTC. Implementation and 31 projection + 6 authored executable tests were then authored; all Rust tests remain uncompiled/unrun. Full Core app transport integration remains separate and unrun unless explicitly executed later.
