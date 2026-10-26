# Evidence-bound correction proposals with transactional compare-and-set

Status: **locally authored implementation and deterministic fixtures; no compile or runtime result**. Independent design challenge completed; implementation review is in progress. This is a standalone authored module; existing user stores and Core are not modified.

## Useful scope, not an invented memory guarantee

Store a proposed correction together with exact quoted evidence and a monotonically increasing per-key revision. A consumer can read the current proposal/revision, prepare a replacement from host-verified quotes, conditionally commit it, and recover the same durable outcome using its operation ID after a lost response. It does **not** judge whether the quote entails the correction, establish source origin, update existing user memories, or turn quoted text into instructions.

Existing Modules `sqlite-memory` exposes append-style remember/recall and creates its store/schema during module registration. Its public memory items do not expose a revision/CAS contract. A read-then-write adapter around that store would not supply the atomic condition we need. This example instead owns a new bounded SQLite database and does no filesystem/database work at module load, tool listing or schema discovery. No Core edits or migration of `.proteus/memory.sqlite`/JSONL stores.

Backend proposal: exact `rusqlite = 0.33.0` with bundled SQLite, the dependency already used by the inspected official SQLite module; its Modules7f lock pins `libsqlite3-sys 0.31.0`. The sole builder resolves and pins the exact new lock. Source readback at rusqlite v0.33.0 confirms NOFOLLOW flags, read-only introspection and transaction rollback-on-drop behavior; blob receipts are in `source-readback/`, not runtime evidence. SDK remains Core3f. No SQLite CLI or upstream suites/scripts required. This is a small new module, not a replacement reference memory implementation.

## Four callable tools, one explicit export

Export ID `memory.correction_cas`, tool/v6. Operator-only config:

```json
{
  "schema_version": 1,
  "store_id": "project-corrections",
  "database_path": "correction-store/corrections.sqlite",
  "evidence_policy": {
    "verifier_tool": "evidence.verify_spans",
    "expected_config_sha256": "<64 lowercase hex>",
    "sources": [{"source_id":"release-note","path":"evidence/release.txt"}]
  }
}
```

Configuration is strict/typed; paths are bounded normal relative components, not request-selected paths. The database parent directory must already exist and be an operator-owned private directory inside the invocation cwd. Initialization never creates arbitrary parent trees. Cwd/path/instance identity is included in outcomes. Config identity uses pinned typed serde serialization, not JCS or a signature. `policy_sha256` fingerprints this entire validated memory-module config, including the expected verifier config digest and permitted source mapping. The operator-supplied expected verifier digest covers the verifier's entire typed config/source list and order; do not reconstruct it from a permitted-source subset.

1. **`memory.correction_init` — WritesFiles**, args `{}`. Explicitly initialize a new, absent database file in that pre-existing private directory. No silent init on read/prepare/apply. Return store label, schema and random database instance ID. Existing valid owned database returns its same identity without migration; foreign/empty/unknown-version files are refused.
2. **`memory.correction_read` — ReadOnly**, args either `{kind:"entry",key}` or `{kind:"operation",operation_id}`. Return typed current revision/proposal/evidence observation, or the durable operation outcome. Missing entries have revision 0; an absent store is an initialization error, not an empty store. Never create or repair a database on reads.
3. **`memory.correction_prepare` — ReadOnly**, args `{key,new_text,evidence}`. Read the current entry revision/instance and invoke the configured registered evidence verifier through the ordinary invocation-bound host callback. Return a typed proposal plus a separate preparation observation. This is the first consumer of the evidence verifier. It grants no write permission and reserves neither revision nor operation ID.
4. **`memory.correction_apply` — WritesFiles**, args `{operation_id,proposal}`. Replay a matching durable operation if one exists; otherwise independently re-invoke the configured evidence verifier, then conditionally commit the proposal and its operation outcome in one SQLite transaction. This is the write consumer, with its own normal host admission/approval. It never trusts a caller-supplied success receipt.

All methods are normal registered tool invocations; no filesystem helper callable from model configuration, no shell fallback, no direct cross-export invocation. Tool metadata declares the read/write safety and exact store path. It does not grant authority. Apply/init advertise no parallel tool-call permission, but SQLite must still handle independent processes/connections correctly. Core continues to own approvals, cancellation, journaling, occurrence identity and settlement.

### Proposal and evidence request

`Proposal` is a strict typed object:

```text
schema_version=1
store_id, database_instance_id, workspace_cwd, database_path
policy_sha256
key, expected_revision
new_text
evidence = {source_id, expected_sha256, claims:[{claim_id,start_byte,end_byte,quote}]}
```

No arbitrary metadata, caller-selected file path, SQL, tool name or prepared success receipt is accepted inside the proposal. `prepare` returns exactly this object, its typed-serialization hash, and a **separate** observation. Apply can receive a manually constructed proposal too; it treats every field as a proposal, rechecks identity and evidence, and relies on host authorization rather than on the prepare hash.

Use the existing evidence tool's strict request schema: one configured source per call, 1–32 unique claims, UTF-8 byte spans, up to 4 KiB per quote / 16 KiB aggregate; source at most 64 KiB. The caller must already know the expected content hash. This prevents a verifier from blessing changed bytes merely by computing a new hash itself.

## Evidence trust and exact consumer checks

The accepted-source `evidence.verify_spans` lives at `../evidence-spans`; runtime acceptance is still pending at design time. No neutral-reader refactor or linking its implementation into this module is required: call the actual registered tool through ToolModuleHost.

Prepare and fresh apply generate their own nested verifier call ID and pass exactly the proposal's evidence arguments. Require successful same-call ToolResult, empty ambiguous structured content, absent error, and no canceled/timed_out/truncated annotations. At top-level metadata allow only the evidence key plus Core's optional `duration_ms` (non-null u64) and optional `output_truncated`, `error_truncated`, `canceled`, `timed_out` (each absent or non-null false bool). Reject unknown decorations rather than silently treating them as benign. This is a dedicated spans-receipt validator, not reuse of the read_file metadata helper. Validate only the structured `proteus.example.evidence_spans` receipt with strict bounded fields:

- schema_version=1, status=`exact_byte_match`, scope=`observed_host_read_bytes`;
- exact current verifier call ID, a valid distinct reader call ID;
- configured source ID, expected verifier config hash, configured path, and observed path equal to invocation cwd joined to that path;
- content hash equal to the requested expected_sha256, bounded source_bytes;
- exact closed set of claim IDs, byte start/end offsets and SHA256 of each requested quote; require start < end, end <= source_bytes and end-start equal to the UTF-8 quote byte length; no duplicate, omitted or extra claims;
- origin_verified=false and semantic_entailment=`not_evaluated` remain explicit.

The registered verifier/read implementation and host AfterTool transformation chain are trusted. A hash is not authenticity. Exact byte matching proves neither origin nor semantic support for `new_text`; the stored record is a **committed proposal with an observed evidence match**, not a proven fact. The verifier may be denied or canceled through normal host policy; no receipt is minted or database mutation attempted on that failure.

There is no transaction spanning the external source file and SQLite. A source can change after the verification read. We store the observation that was made, not a claim that the source remained current at SQL commit. A preparation observation is not reused as fresh evidence during apply.

## Real transaction, operation identity and outcomes

Three fixed tables, with parameters for all data and no dynamic SQL identifiers:

- `store_meta`: singleton schema version, configured store_id, generated 128-bit instance_id, initialization workspace cwd, configured database path and full immutable memory-policy hash;
- `entries`: key primary key, revision, last_applied_operation_id;
- `operations`: operation_id primary key, canonical request bytes, request SHA256, stable outcome JSON, and bounded evidence-observation JSON for applied/conflict decisions.

Schema enumeration includes every object, not a LIKE-prefix filter. These two
WITHOUT ROWID primary keys and the metadata INTEGER PRIMARY KEY need no separate
schema index entries, so exactly three objects are expected. [SQLite schema table](https://www.sqlite.org/schematab.html)

Entry contents are obtained by joining their last applied operation; no second inconsistent copy of the proposal text. Revision starts at 1; absence is 0; no delete/reset API. Revisions use SQLite's nonnegative signed integer range; exhaustion rejects instead of wrapping. New database initialization produces a new instance ID, so a proposal for a replaced database cannot silently target revision 0 in a new one. Store metadata and proposals bind exact workspace cwd plus configured database path. Moving/copying the store to a different cwd/path is refused, not treated as a migration; another database cannot satisfy a proposal merely by sharing a store label. First-batch store policy is immutable: every open checks the full memory-config hash stored at init. Workers configured with different verifier/source policies cannot silently share that store. Policy rotation/migration is a separate future explicit operation, not an implicit reconfiguration path.

A fresh apply has these phases:

1. Validate complete input bounds/shape, derive canonical request bytes and hash. Outer invocation/callback IDs are **not** part of the stable request identity. Include store/instance/cwd/path/policy/key/expected revision/new text and all evidence claims. Compare stored canonical bytes as well as hashes: digest collision is not the correctness condition.
2. Open the already initialized database read-only, validate its identity/schema, and look up operation_id. Every open requires the immutable store-policy hash from initialization, so a changed memory policy does not silently replay an old outcome. Recovery uses the same explicitly configured original profile. If found, identical bytes return the persisted business outcome; different bytes produce `operation_payload_mismatch`, with no verifier call and no update. A replay is not a fresh evidence verification. Its outer ToolResult call_id is the current host call; a separate audit flag may say replayed, while the stable business outcome is unchanged.
3. For a new operation, require current instance and policy identity, then invoke/validate the evidence verifier. Drop all read statements, read transactions and the read-only connection before the host callback: hold **no SQLite connection/transaction lock across the evidence execute_tool callback** (bounded cancellation polling still occurs inside write transactions). On validation/permission/cancellation failure, return no committed-operation receipt.
4. Check cancellation and repeat a read-only schema/expected-instance check after the callback, dropping that connection before proceeding. This refuses a newly replaced/hot-journal store before a read-write open could recover it. Then open a write connection without CREATE and begin an **IMMEDIATE** transaction. On that actual write connection, inside the transaction, revalidate the complete schema, store_id, database instance, exact cwd/path and immutable policy identity against the proposal/config **before operation lookup or any application mutation/persistent PRAGMA**. This is mandatory even after a prior read-only check: the callback interval can contain a legitimate store replacement. Recheck operation ID/bytes inside this transaction (another invocation may have committed while verification ran). If already present, replay/reject as above without applying again. A racing caller may already have performed its verifier callback before discovering the winner; only the already-durable fast-path replay guarantees no new callback. Its stable outcome is still the winner's persisted observation, not the losing caller's observation.
5. Read current revision inside that same write transaction. If equal to expected_revision, conditionally insert/update the entry, verify exactly one affected row, and insert an `applied` operation outcome atomically. If unequal, leave the entry unchanged and insert a `conflict` outcome with the actually observed revision. Both terminal outcomes bind the operation ID permanently. Capacity checks and revision overflow checks occur in the transaction. Construct and validate all stable outcome, observation, row and outward response bytes/bounds before the entry/operation SQL writes and commit, so an ordinary response-shape/size error cannot first be discovered after commit.
6. Poll cancellation before mutations and immediately before commit. Commit entry change + operation row together. Return a committed outcome only after successful commit. No application-level retry loop around an unknown commit result.

SQLite allows one writer at a time; BEGIN IMMEDIATE obtains write-transaction admission rather than performing an unsafe read-upgrade sequence. Busy and transaction-error handling must remain explicit. [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html)

Stable `Outcome` fields: schema_version, store_id, database_instance_id, workspace_cwd, database_path, operation_id, request_sha256, key, expected_revision, observed_revision, decision (`applied`/`conflict`), resulting_revision (for applied), proposal_sha256 and evidence-observation digest. No wall-clock freshness claim. The actual observation may retain original verifier/read IDs; it is clearly historical on replay and does not masquerade as a receipt for the new outer invocation.

**Conflict is a durable terminal result**, not an instruction to retry against a newer revision. Exact replay returns that same historical conflict even if the entry later changes. To propose against the new revision, read/prepare again and use a new operation ID. Changed key, revision, text, source/hash/quote/span, store instance or policy identity under an already bound operation ID is rejected.

An operation ID is bound only when an applied/conflict transaction commits. Invalid requests, evidence failures, known rollback, busy or storage errors do not create a successful cache entry. After an ambiguous response/error, retry the **same ID and same payload** first. An absent read result alone does not establish that a concurrently running original invocation cannot still commit. The transaction recheck ensures only one payload can win one ID; there is no synthetic lease or orphaned `pending` state.

## Storage, errors, cancellation and authority limits

- Explicit init uses exclusive file creation; it refuses an existing unknown file. SQLite open does not use URI interpretation or attach other databases. Existing files are first checked read-only; unknown schema/identity is refused before a write connection or persistent PRAGMA/schema change. The actual write connection is revalidated again inside its transaction. Owned schema is checked before writes; unexpected tables/views/triggers/schema versions refuse. No migration/repair/delete/vacuum command.
- Before opening an existing file with SQLite, perform a bounded read-only header preflight (SQLite magic, 4 KiB page size, rollback read/write format bytes at offsets18/19, module application/schema marker, file-size cap). Reject WAL/unknown format before SQLite can create auxiliary files. A nominal SQLite read-only WAL open may create `-wal`/`-shm`, so READ_ONLY alone is not our zero-write boundary. This preflight supplements, never replaces, SQL schema/identity validation and the trusted-directory assumption. [SQLite WAL read-only behavior](https://www.sqlite.org/wal.html#read_only_databases), [database header format](https://www.sqlite.org/fileformat.html#the_database_header). Read connections use READ_ONLY, no CREATE. Write connections must positively verify `is_readonly(Main)==false`, since SQLite may downgrade a requested READWRITE open when OS permissions forbid writing. Exclusive initialization uses Rust create_new, not SQLite OPEN_EXCLUSIVE (which is not an exclusive-create guarantee). [SQLite open flags](https://www.sqlite.org/c3ref/open.html) Journal mode is fixed DELETE, synchronous FULL for writes, trusted_schema OFF, fixed SQL, bounded busy timeout (proposed 100 ms), bounded page count. WAL or unknown pre-existing mode is refused, not silently converted. Read-only recovery that needs writes returns an error; no repair under ReadOnly safety. A fresh apply also begins with a read-only identity check and may therefore refuse a crash-damaged/hot-journal store instead of automatically repairing it. Automatic crash-repair is not a claimed feature of this first version.
- Resolve the configured path under actual invocation cwd; reject traversal, symlink components/leaf, non-regular files and (on supported Unix hosts) multiply linked database files. Use SQLite NOFOLLOW where supported by the pinned library. The directory must remain operator-controlled; creation uses owner-only file permissions on supported Unix hosts. Ownership/schema/instance markers are not authenticity checks against another writer with filesystem access. External database tampering or restoring an older backup can invalidate monotonic-history/idempotency assumptions. In particular, restoration at the SAME cwd/path with the SAME instance ID is undetectable here and can erase operations/revisions. This version has no external monotonic authority or restore/rollback-protection API and makes no exactly-once claim across such restoration. Path checks alone are **not** a race-proof sandbox against a hostile same-UID process swapping parent directories; no custom VFS or Core filesystem authority is invented. Initial supported runtime can be Linux only if needed for the stated checks.
- Init may fail after exclusive empty-file creation but before schema commit. Do not relabel that artifact as a valid store or silently repair/delete it later. Report initialization failure; an operator must reconcile the owned incomplete file. Normal apply never initializes a missing/empty database.
- Before the transaction's commit point, observed cancellation attempts rollback through the pinned transaction's rollback-on-drop behavior. Drop ignores rollback errors; no proof against arbitrary storage/VFS failure is claimed. Cancellation, process death or transport loss after commit can hide a real committed effect from the caller. Do not claim that cancellation implies no write. The durable operation result is the recovery mechanism, not a bypass of Core's cancellation/settlement.
- SQLite's atomicity/durability relies on its VFS, OS locking and flush behavior. We will test bounded failure injection and restart/replay, not claim a proof against arbitrary filesystem/hardware faults. [SQLite atomic-commit assumptions](https://www.sqlite.org/atomiccommit.html)
- Storage errors distinguish `busy`, `capacity`, `invalid_store`, `not_initialized`, `revision_exhausted` and generic I/O/commit-unknown. Do not automatically reopen another database, create a fallback file or retry under a new operation ID. Bounded rollback is attempted on known transaction errors; uncertain outcome is reported as such and recovered by identical retry.

Proposed fixed caps for the first batch: 256 keys, 1,024 durable operation IDs, key128 ASCII bytes, operation/store IDs64 ASCII bytes, new_text4 KiB UTF-8, canonical proposal32 KiB, evidence receipt32 KiB, stable outcome4 KiB, database16 MiB (4,096 pages at 4 KiB), read/operation response96 KiB. No automatic operation eviction: evicting an ID would undermine idempotency. SQLite rollback-journal/transient overhead is additional to the database cap and must be documented. Reject on any cap rather than truncate. No claim of a strict whole-process memory bound.

## Authored validation targets (none run yet)

1. Module load/list has zero DB/parent creation; read/prepare do not initialize; init creates only the exact absent file in own temp directory, returns same identity on repeated valid init, rejects foreign/empty/symlink/unknown schemas without mutation. A valid owned-schema WAL-mode fixture must fail before opening with SQLite and create no new WAL/SHM files; retain a valid rollback-mode positive control.
2. Real SQLite: absent revision0 → apply revision1 → read exact proposal/evidence; expected1 update→2; stale expected0 conflict leaves current entry intact; no ABA/reset/delete API.
3. Exact operation replay across new connections and process restart yields byte-identical stable outcome, unchanged revision, zero verifier callbacks. Changed payload under that ID rejects each independently targeted field. Replaying a conflict stays conflict after later updates.
4. Two independent connections/worker invocations race on the same expected revision: exactly one applied, other conflict. Same ID/same bytes commits once and replays; same ID/different bytes admits only one and rejects the other. Do not substitute a single in-process Mutex simulation for the SQLite transaction.
5. Evidence negative controls with otherwise-valid actual/synthetic-host result: wrong current call ID/config/path/source/hash; duplicate/omitted/extra claims; changed offsets/quote hash; flagged truncation/cancellation; false origin/entailment marker; plain-text success/forged caller receipt. No DB entry/op outcome on verifier failure. Include callback-driven replacement of validated instance A with separately initialized instance B at the same configured cwd/path; keep verifier evidence valid, require exact instance mismatch on the write connection, and prove B's entries/operations unchanged.
6. Cancel before verifier, after verifier/before transaction, after entry SQL/before op insert, before commit, and after committed effect/before response. Authored deterministic failure seams must prove rollback or replay recovery, never count cancellation as successful execution.
7. Busy writer and capacity/revision bounds have exact diagnostics plus valid maximum controls; errors do not convert to success or recreate the store. Lost-response/restart tests retain the same ID and payload.
8. Callable end-to-end use case with an owned text artifact and configured evidence verifier: prepare → host-approved apply → read → exact replay → concurrent stale correction conflict. Source matching remains syntactic, semantic_entailment=not_evaluated.

Builder alone compiles/runs after independent source review and exact dependency/CI scope approval. Evidence-spans runtime must be validated before any claim that its real consumer pairing passes. Authored deterministic fixtures can test policy/schema/transaction logic meanwhile; they are labeled synthetic host evidence, not real official-reader runs.

## Alternatives considered / review questions

- Existing remember_fact/recall + compare in application: rejected, not atomic and no durable operation identity.
- Model-provided verifier receipt accepted at face value: rejected; re-invoke trusted registered verifier. Hash/signature-shaped strings are not authority.
- Hold write lock while verifying: rejected; expensive/cancelable host callbacks would unnecessarily block other writers and couple liveness.
- Persist `pending` reservations before verification: postponed; leases/attempt recovery would add a second state machine and could fake Core-owned cancellation semantics.
- Automatic schema creation on apply/read, or implicit migration: rejected. Explicit init makes filesystem effects visible and bounded; incomplete init remains an honest operator-reconciliation gap.

Reviewer challenge requested: (a) transaction/operation-ID binding point and conflict caching; (b) receipt correlation versus historical replay; (c) exact read-only/open/initialization safety and incomplete-init recovery; (d) path/OS assumptions; (e) whether four tools are the smallest useful callable workflow. These choices received design clearance; implementation/source tests still require independent review and execution.
