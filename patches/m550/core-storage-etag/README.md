# Core / Contracts: encode a storage ETag into one final string

The canonical representation, SHA-256 digest, lowercase alphabet, ordering
rules and receipt comparisons stay unchanged. Only the presentation step in
`storage_value_etag` changes: reserve exactly twice the digest length and
emit both ASCII nibbles directly instead of allocating a formatted string
per digest byte and growing the collector. This is the storage
read/cache/write contract, not the earlier session-selection digest change
(#534); it neither touches nor counts that previous code.

**Proof.** Both the exact M350 and the patched production functions are
compiled side by side in locked release mode. A synchronous native System
allocator meter surrounds each real public-call evaluation; independent
canonical compact JSON and one-shot SHA-256 are the oracle. Across 4,104
values in each of the default and explicit JSON preserve-order modes, each
digest matched exactly, including the repository's known answer; the corpus
covered all 256 digest byte values, nested reversed keys, escapes, Unicode,
empty values, a 1-MiB scalar and a 50-row nested page. Every case removed
31 allocation calls and 3 reallocation calls and reduced gross requested
bytes by 304. Scalars went from 32 allocations + 3 reallocations to one
64-byte output allocation. Object sorting and other pre-existing allocations
remain unchanged (the 50-row page had 132+3 to 101+0). These figures describe
allocator requests per operation, not resident memory, wall time or a
whole-application total. The genuine Contracts session-storage tests check
the public receipt-validation route separately. Only the content of the
designated value_hash.rs differs in the exact production crate compiled for
those tests.

**Replay.** Put original value_hash.rs under before/ and the patched file
under after/ alongside proof/. In proof/, install native-proof.rs,
proof-Cargo.toml and proof-Cargo.lock as main.rs, Cargo.toml and Cargo.lock.
Run `cargo run --release --locked` and repeat with `--features preserve_order`.
Run the real repository's Contracts library tests filtered to
`contracts::session_storage::`. Byte order, cache format and validators are
unchanged. No new dependency.
