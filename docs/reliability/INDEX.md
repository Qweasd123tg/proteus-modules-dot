# Reliability evidence: publication map

**Snapshot: 2026-10-26. This is a summary candidate, not a new publication or deployment.** It indexes distinct accepted evidence types without turning them into an aggregate speedup, bug count or test total. Exact evidence/review hashes and source links are in [evidence-map.json](evidence-map.json).

Pins below mean *inspected versions*, not “latest.” Most evidence is unpublished: its SHA256 identifies a retained receipt, not a public download, an authenticity signature or an upstream endorsement. The native-cache entry has existing public code/CI links; that does not mean the other studies were delivered in the same commit.

## What a reader can rely on

| Topic | Evidence class | Supported use | Important boundary |
|---|---|---|---|
| [SessionStore growth and ownership](#sessionstore-growth-and-ownership) | Actual unchanged Core, authored local fixture | Understand selected writer/rollback behavior and requested-allocation growth | Debug requested bytes are not RSS or a speedup |
| [Native read-cache](#native-read-cache) | Actual unchanged Core, authored CI fixture | Choose among existing read APIs with known semantics | Cached view and strict projection are not interchangeable work |
| [Queue ownership](#queue-ownership) | Executed pure model + source-only consumer trace | Design credit transfer through a UI batch | Not an implemented Desktop fix or physical memory cap |
| [Outcome and activation](#outcome-and-activation) | Source-only lifecycle studies | Separate retry, reload, admission and rollback decisions | No cancellation/reload runtime or universal effect rollback proof |
| [Composed budgets](#composed-budgets) | Source-only clock/counter mapping | Review deadlines, retries and usage labels | Not a global quota or end-to-end runtime guarantee |
| [Evaluation and report interpretation](#evaluation-and-report-interpretation) | Source-only evaluator study; separate authored synthetic consumer | Avoid false task-success verdicts | Reported consistency is not independent objective evidence |
| [Retrieval profiles](#retrieval-profiles) | Source-only consumer study; separate actual reference engine | Preserve intentional matching/order semantics | Not official Rust backend equivalence, relevance or speed evidence |

## SessionStore growth and ownership

The same authored public-API fixture exercised Core `3f36a003` and `1fc3ef2`. It observed initialized-writer ownership surviving public-handle drops until owner exit, plus rejection/rollback controls that preserved committed state and later valid progress. Bounded growth workloads used canonical facts, **not per-token journal writes**. The full validation/durable-before-publication boundary remained intact. [Pinned writer ownership](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_store/writer.rs#L35-L50).

Two different observations must stay separate:

- **Requested allocation:** cumulative allocation/reallocation sizes, including ancillary runtime work. Not resident memory, live-memory accounting, bytes actually copied or isolated validation cost. Relaxed multi-counter reads are not a coherent live-memory snapshot.
- **Elapsed call time:** whole calls in an unoptimized development profile, including required durable sync where applicable. Small sequential samples and shared-host/cache conditions do not establish causal improvements, p95, release latency or a production SLA.

No local raw journal or path-bearing log is included here. Hashes identify the historical and inspected-pin batches separately; the older report's then-pending cache work remains historical, not silently rewritten.

## Native read-cache

An existing [public authored CI run](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40248855203) used exact [commit5901a601](https://github.com/Qweasd123tg/proteus-modules-dot/commit/5901a6013a4578d38a1e8afd65daf2a207eaed09) against Core `1fc3ef2`. Public APIs produced the native cache. The retained evidence distinguishes correct cached conversation results, successful/failed append behavior, invalid-cache fallback and strict canonical corruption diagnostics.

Separate owned-child open diagnostics showed the valid snapshot using the native view without opening its canonical journal, the strict positive control opening the journal, and the schema-invalid view opening both. This is more than equality alone, but **not zero filesystem I/O**. Trace diagnostics were not timing samples.

Whole-call requested bytes and elapsed observations remain different quantities. Native transcript checks covered message count, not full transcript DTO equality; nonempty usage and complete model-context equivalence were not tested. Choosing a display/read API is not permission to replace strict authority validation. Links identify recorded public source/CI; no claim is made that downloadable CI artifacts remain available forever.

## Queue ownership

The pinned Desktop [producer](https://github.com/Proteus-harness/Proteus-desktop/blob/1c1082050f307df6b798ada74855b13b6eeb4d5a/src/connection.rs#L113-L159) and [UI consumer](https://github.com/Proteus-harness/Proteus-desktop/blob/1c1082050f307df6b798ada74855b13b6eeb4d5a/src/ui/chat/pump.rs#L18-L40) were traced read-only. A separate authored model keeps queued **and leased** payload credits charged until valid apply/abandon, with independent consumer-ownership checks and a separately bounded producer frame.

The executed model and its causal mutants are not actual Desktop mutations. They establish only their exact logical-payload invariant, not RSS, an SSE implementation, real cancellation or UI fairness. A production frame cap alone could repeatedly reject a legitimate growing full-history baseline; compatible paging/exhaustion behavior and real scheduler/lease integration remain unresolved. No arbitrary dropping policy is recommended.

## Outcome and activation

The outcome study compares selected pinned Core, Codex and OpenHands paths. A transport error is not necessarily rejected admission; a generic timeout/cancel result is not proof of no external effect; raw/final accepted result records are not automatically physical-effect receipts. Broker lifecycle bookkeeping and cooperative grace timers do not establish physical stop of arbitrary descendants. Use the existing admission/settlement evidence before separately authorizing retry. [Core invocation boundary](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/invocation.rs#L28-L124).

The activation study compares Core and pinned Pi. Candidate construction, coherent publication, admission snapshot selection and retained in-flight ownership are distinct. Keeping the old selected registry after a hard preparation failure is not rollback of every process/file/external effect, and availability refresh is not universal authority revocation. MCP termination is an awaited attempt, not an unconditional successful-stop barrier. [Core publication boundary](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/runtime/reload.rs#L31-L91).

Both are **source studies**. Their proposed causal runtime scenarios remain unrun; this index supplies operator distinctions, not a newly reproduced cancellation/reload defect.

## Composed budgets

The source ledger tracks owner, value/unit, start/reset point, zero semantics and enclosing coverage for workflow, hooks, model/context/tool calls, broker nesting, children and provider retries. An await outside a local timeout select can still be covered by an enclosing timer; synchronous spawn and cooperative polling require separate qualifications. Broker pending-root capacity includes active roots rather than an additional queue on top. [Reviewed-workflow source](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/reviewed_workflow.rs#L44-L168).

Finite call-count reasoning applies only to the selected effective constructor/workflow/provider configuration. Canonical exchanges are not provider attempts or billing coverage: a request can be recorded before network start, and retries can occur within one exchange. No global budget service, worst-case cost guarantee or composed runtime test is supplied.

## Evaluation and report interpretation

The source-only Core/Modules/SWE-bench study separates protocol delivery, canonical settlement, replay consistency, project-command status, independent objective validation and evaluator infrastructure health. A replay can correctly match an Error; an eval/report command can return successfully while reporting an unsuccessful result. Do not derive task success from exit zero or optimistic prose. [Core eval predicate](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/eval_report.rs#L38-L90), [pinned benchmark grading conditions](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/grading.py#L113-L176).

A separate bounded Python classifier was actually exercised with **synthetic** replay-report inputs. It accepts only the explicitly covered source/shape and preserves *reported match/divergence* separately from unknown primary evidence. Unsupported Core eval/project-check JSON shapes remain unknown; no arbitrary nested `success` search or producer execution occurs. It is a report interpreter, not an objective verifier or authentication layer. No benchmark task or live Core report producer was run by these packages.

## Retrieval profiles

The source study traces query normalization, scope, ordering, truncation and context admission. It keeps implementation-specific qualifiers: the rg polling timer is not a whole-call cleanup bound; context dedupe uses an unframed newline key; instruction retention uses a metadata convention, not authenticated provenance. The proposed official-module/context observations remain unrun.

The later accepted **authored reference** used installed Python3.12.14/SQLite3.53.1 FTS5 with a tiny fixed in-memory corpus and an in-memory JSONL reference. It observed selected ASCII differences: literal substring versus token-prefix AND, content-only versus kind+content scope, case matching, and original versus descending-ID empty-query order. Complete-store controls distinguished negative matches from an empty database. [Pinned SQL and query source](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/context_provider/sqlite-memory/src/lib.rs#L116-L188).

This is not a Rust Modules run or equivalence proof. Python binding/engine, ASCII subset and ordinal timestamp deviations are explicit; nonempty result sets do not assert rank-tie order. There is no real-project recall/relevance/ranking score or performance trial. A backend replacement must declare intended semantic changes rather than present a different retrieval profile as “the same, faster.”

## Publication boundary

Only this index and its small evidence map are candidate payloads. Existing accepted sources, receipts and raw evidence remain in place; no raw traces, journals, caches, local paths, process logs, complete source bundles or private findings are copied. A later publication must preserve the classifications and hash identities, and needs its own authorized exact-head review. This map does not rerun evidence, refresh external versions, create a branch/PR, merge changes or imply that unpublished implementations were delivered.
