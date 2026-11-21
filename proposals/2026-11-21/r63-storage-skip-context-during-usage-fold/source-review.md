# R63 storage replay source boundaries

- Modules exact main: 9469e3b12529d08b1f4a76882693e2065e842c51;
  pinned contracts and journal/session semantics: Core SDK
  0c1b7572313230e5d123e95c722e1258a2e9ecd6.
- journal/projection/sequence.rs performs mandatory canonical semantic
  validation before Fold updates either a ModelContextProjection or
  UsageProjection. These are separate fields. ModelContextProjection::apply
  in model_context/projection.rs reads only the already validated JournalRecord
  and mutates its private lineage/observations/turn checkpoint. It does not
  read or write a file, validate another domain, emit an event, return an
  error, or supply data to UsageProjection.
- journal/usage.rs::UsageProjection::apply uses the same validated records
  and the same usage state before/after. The resulting usage serializes
  by the existing SessionStorageResponse implementation.
- The same fold body clears the pending page cursor and trust bit, resets
  the pinned backend, reads through EOF/SHA, validates all sequence, schema,
  semantic/revision and changed-source fences, and only then marks the
  snapshot verified. The new usage method returns only usage; it does not
  retain a partial Fold on SnapshotState. Later context or full-state
  requests still take the unchanged full projection, and terminal page
  capture still selects the full projection mode.
- The real Core fallback is RemoteSessionStore::usage_snapshot after
  fresh_read_usage misses. The R59 125k preferred restore/resume op trace
  does not contain ReadUsage. This is a targeted usage fallback optimization,
  not a claim that selected startup workload benefits. Do not conflate
  whole-journal validation with the removed projection visits.
- Reviewed an otherwise wholly redundant second seek to byte zero after
  unhinted JSONL fingerprint capture; it is only one call per snapshot and
  was not made a candidate this round.
