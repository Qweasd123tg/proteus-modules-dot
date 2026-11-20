# R22: 1 MiB batches for an already validated display cursor

Local experiment, not a production change. Only the **normal batch byte target** of
an existing detached worker's ReadDisplayRecords path changes. Canonical reads,
foreground commits, the 64-record request from Core, the normal 4 MiB contract
limit, the 65 MiB cap for a single record, and the 512 MiB storage staging budget
are unchanged. The display cursor still revalidates its physical prefix and can
hold a pending decoded record when it crosses a byte target; this is not a heap
or PSS bound. Returning fewer records at the same revision is allowed.

Reconstruction: Modules base cf999371f6e564376565738bebc3416aad12f908 plus
detached-baseline.patch (sha256 ffaa9877ccc49fb8d806e18c83be535986a56b1ec74c19317ffcb35446b65030)
gives tree 5261c122a6ed19676c00c8ca6ada3ecf1af3dd15. Apply page-target.patch
(sha256 139bd67d3b64f3f69ba87f8b8b52a54aef847ae1812b062a0033083b5f367318)
to that tree → 2d6db9528bf6252bd29dfe35bcc18fbd687729eb. SDK and contracts
remain pinned to 0c1b7572313230e5d123e95c722e1258a2e9ecd6, not the host Core.
worker-page-1m sha256 8956a15b85fae57ade51fd0a7bc57a6934107c86937595918dd9c38d7221c6d4.
Local build: cargo build --offline --locked --release --jobs 1 -p proteus-session-storage-module;
CARGO_INCREMENTAL=0, RUSTFLAGS="-C link-arg=-fuse-ld=lld". No allocator or runtime settings required.

Focused cursor test covers JSONL and SQLite. It compares every record to an unmodified canonical
page, including an indivisible record of >1 MiB, checks pagination and the terminal cursor,
and rewinds. cargo test --offline --locked --jobs 1 -p session-storage --lib --
--test-threads=2: 67 passed, one existing manual performance case ignored. See storage-tests.log.
The detached experiment's existing same-session conflict and canonical-open fallback restrictions
remain. No contract validation, identity, or activity/staging policy relaxations.
