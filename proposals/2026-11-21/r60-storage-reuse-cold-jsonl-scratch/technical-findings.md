# R60 canonical JSONL: bounded scratch for a strict display capture

Exact Modules baseline is 9469e3b12529d08b1f4a76882693e2065e842c51
with pinned contracts / session semantics / module SDK from Core 0c1b757.
No timing, no quota change, no remote action. The local proposal is
independent of #331 (scratch for *decoded staging pages*) and #348 (cache
publication pathname reuse). #250 already removes one allocation from the
compact inline size test. #256 already borrows complete lines contained in
the BufReader; the overlay below touches only remaining fallback allocation
in that path and must be applied after #256, not on top of the standalone.

## Fixed-scope change

Give the single canonical sequence traversal of OpenDisplaySnapshot an
empty caller-owned scratch Vec via RecordSnapshot's default delegating
method. SQLite delegates to the prior method without touching it. JSONL
retains at most 128 KiB of acquired capacity between reads of that request
and releases any larger capacity after processing the line. Both the bound
of the current line and all hash, schema, raw bytes, session, sequence,
semantic fold, external payload, append-freshness, and EOF/root proofs stay
where they were. The scratch is local and dropped before source recheck,
catalog/head publication, and snapshot retention. No scratch lives on any
snapshot. The next method outside full display capture uses a fresh zero-
capacity Vec per call as before.

The same change was instantiated as an exact-main variant and an
after-#256 variant. Only one is to be applied/countable. In the latter,
the borrowed-line path is unmodified and passes an out-of-buffer row to
the existing bounded read/decode/error logic. The current composition
target is the separately copied R59 M150 preflight Modules source, which
contains #256, #331 and #348, not a mutation to its frozen tree.

The sealed private JSONL fixture is regenerated with the stock durable
writer, 1,251 lines, 52,592,436 bytes, 42,140 longest line and exact
e00e71759cfda4f4982c5d2f9f4790bed78a7fb0e8cab22e0e96d03c8dbf4c61
SHA. In fixed 64 KiB chunking, 802 lines cross one such boundary. This
offset calculation motivates measuring the fallback, but is not an
allocator measurement or a syscall count.

## Candidates ruled out

Do not remove the initial hash from a normal capture: it constitutes the
pinned prefix before decoding/semantic errors; replacing it with the
streamed digest alone would change validation order and race evidence.
Do not count raw inline bytes instead of normalizing parsed JSON:
whitespace, escapes and existing compatible map/number behavior can
create different compact serialization lengths, and #250 preserves the
exact limit without a new output Vec. Do not add typed schema-specific
hacks or rewrite the reader around current fixture records to avoid
Value conversion. Such changes need their own compatibility and contract
proofs. R59 phase ordering is a diagnostic lead only.
