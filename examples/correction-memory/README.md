> **Separate raw-argument compatibility revision, uncompiled/unrun.** Frozen R17 is unchanged. See [RAW-COMPATIBILITY.md](RAW-COMPATIBILITY.md) for the source-proven SDK refusal, pinned Core admission order and bounded fix. This candidate contains69 authored/unrun tests; no new runtime acceptance is claimed.

# Correction proposals with SQLite compare-and-set

**Source candidate. Rust has not been compiled or run.** Linux-only first batch.
This is an independent example, not a migration of existing user memory.

An agent can prepare a proposed correction from exact quoted evidence, apply it
only against an expected revision, and recover its original durable outcome by
replaying the same operation ID and payload. A stale revision creates a durable
`conflict`, not an automatic overwrite. Quoted evidence is **not semantic proof**
that the proposed prose is true.

## Callable workflow

Export `memory.correction_cas` (tool/v6) registers:

| Tool | Safety | Effect |
|---|---|---|
| `memory.correction_init {}` | WritesFiles | Explicitly create the configured new SQLite store. |
| `memory.correction_read` | ReadOnly | Read an entry/revision or historical operation outcome. |
| `memory.correction_prepare` | ReadOnly | Read revision, invoke the registered spans verifier, return a proposal. |
| `memory.correction_apply` | WritesFiles | Re-verify evidence; atomically commit proposal or conflict, or replay an existing outcome. |

Registration and tool listing do not touch the filesystem. No read/prepare/apply
silently initializes a missing store. Tool safety declarations describe effects;
they do not grant permission. Host policy must separately admit init/apply and
nested verifier/reader calls. No shell, external hook, network model or filesystem
fallback for evidence is implemented.

Example operator config (supply the **whole verifier config's** actual digest):

```json
{
  "schema_version": 1,
  "store_id": "release-proposals",
  "database_path": "store/notes.sqlite",
  "evidence_policy": {
    "verifier_tool": "evidence.verify_spans",
    "expected_config_sha256": "<64 lowercase hex>",
    "sources": [{"source_id":"release","path":"evidence/release.txt"}]
  }
}
```

The operator first creates a private owner-only `store/` directory inside an
absolute canonical invocation cwd. The module creates only the configured absent
database file (0600). Cwd, relative path, random database instance, schema, store
label and complete memory-policy digest are immutable store identity. Reconfiguring
that policy, moving the database, or proposing against a replacement instance is
refused. Recovery uses the original explicitly configured profile; there is no
implicit policy rotation or schema migration.

See [USECASE.md](USECASE.md) for prepare → apply → replay → stale conflict.

## A useful but deliberately limited evidence consumer

Fresh prepare/apply invoke `evidence.verify_spans` through `ToolModuleHost`.
No caller-provided receipt can substitute for that invocation. The consumer binds
the current nested call ID, full operator config digest, source ID, exact configured
and observed path, expected content hash, and exact closed claim set/offsets/quote
hashes. Unknown metadata, partial/truncated/canceled results and ambiguous typed
fields fail closed. Optional Core `duration_ms` and explicitly false known status
flags are supported.

`origin_verified=false` and `semantic_entailment=not_evaluated` remain explicit.
The verifier, reader and host result-transformation chain are trusted. Hashes are
correlation, **not authentication**. A source may change after verification and
before SQLite commit: this is an observation, not an atomic filesystem snapshot.
Returned/stored text is proposed data, never promoted to system instructions.

## What the transaction guarantees—and does not

- Real `rusqlite = 0.33.0` bundled SQLite, fixed parameterized SQL. No shared-memory
  mutex stands in for database concurrency.
- Every fresh apply rechecks expected revision inside `BEGIN IMMEDIATE`. Entry
  update and terminal operation outcome commit together. Applied revisions increase;
  absent is 0. No delete/reset API exists.
- Exact replay compares canonical request bytes **and** their hash. It returns
  the same stable business outcome and original historical observation, not fresh
  verification. Already-durable fast-path replay makes no verifier call; a racing
  invocation may already have verified before discovering the winner in its tx.
  Typed serialization preserves array order: reordering claims changes the
  operation payload even though receipt claim coverage is compared as a set.
- Changed payload under a bound operation ID is refused. A conflict is permanently
  bound too; read/prepare again and choose a new operation ID for another attempt.
- All SQLite read handles are dropped before the evidence callback. Cancellation
  polling occurs inside transactions; no arbitrary evidence work holds a DB lock.
- After the callback, a read-only identity check precedes write-open; the actual
  write connection revalidates schema/instance/location/policy **again inside its
  transaction**. A valid receipt for instance A cannot authorize mutation of a
  newly initialized instance B at the same path.
- Ordinary response/outcome size checks precede commit. Observed precommit
  cancellation attempts rollback (the authored fault tests assume working local
  storage). Cancellation, transport loss or process failure after
  commit can hide a real effect: retry the **same ID and same payload**. An absent
  operation read does not prove another in-flight request cannot later commit.
- Busy/storage failures do not become success or trigger a new-ID retry. Commit
  errors are conservatively `commit_unknown`; recovery is an identical retry.

No exactly-once claim across external tampering or restoring an older backup at
the same path with the same instance ID: this version cannot detect that rollback
or restore erased operation history. SQLite/OS flush and locking assumptions still
apply. There is no external monotonic authority.

## Filesystem and resource boundary

Existing files get a bounded read-only SQLite-header check before SQLite opens:
4 KiB pages, owned schema/application markers and rollback format only. WAL is
refused before a nominal read-only connection can create WAL/SHM files. Unexpected
schema, symlinks, hard-linked files, non-private file/parent permissions and foreign
identity refuse. `READ_ONLY` opens never create or repair a store. An incomplete
explicit initialization may leave an unusable file; automatic repair/deletion is
not provided. A hot journal needing writes can also cause refusal.

Parent directories must remain trusted and operator-controlled. Checks plus
NOFOLLOW are not a race-proof sandbox against a hostile same-UID directory swap.
No custom VFS, broader Core filesystem authority, arbitrary database migration,
extension loading, ATTACH, URI filename or SQL interface is supplied.

Fixed caps: 256 keys; 1,024 retained operation IDs; 16 MiB database; 4 KiB proposed
text; 32 KiB canonical proposal/observation; 4 KiB outcome; 96 KiB response; 64 KiB
raw verifier response. Evidence allows 32 unique claims, 4 KiB each/16 KiB total,
source ≤64 KiB. All caps are conjunctive, not a promise that every combination of
individual maxima fits the store. No eviction/truncation. SQLite journal/transient
space is additional. SDK inputs are already allocated before module validation;
this is not a whole-process memory cap.

## Authored validation, still unrun

The tests use owned temporary SQLite files. Coverage includes independent-connection
revision/operation races, exact durable replay/conflict, store replacement during
a valid verifier callback, read-only/WAL/schema/path refusals, response bounds,
precommit rollback, postcommit response loss, maximum capacities/revision, targeted
receipt failures and an actual own-binary SDK restart/cancellation fixture.

The `correction_workflow` example and `actual_modules` tests additionally call the
unchanged actual evidence-spans module through an **authored** in-process callback
router and reader of a newly created temporary artifact. They are not Core routing,
approval, journal or official read_file tests. The verifier itself remains runtime-
unvalidated until the separate build queue executes its frozen source tests.

After the sole builder generates/reviews the lockfile and source is accepted:

```sh
cargo test --locked --all-targets
cargo run --locked --example correction_workflow
```

Those are proposed commands, not recorded results. No Cargo/build/CI has run for
this crate. See [DESIGN.md](DESIGN.md) for source-grounded semantics and unresolved
operational boundaries. No publication or deployment is implied.
