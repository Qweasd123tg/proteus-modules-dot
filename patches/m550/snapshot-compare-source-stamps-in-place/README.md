# Compare snapshot source stamps without a temporary Vec

For the warm and cold rechecks in ordinary snapshot preparation, compare the
existing fixed journal/WAL/manifest stamp array with the expected slice.
The first owned stamp list, publication conditions, filesystem probes, and
errors stay as before. This is separate from durable catalog read/write checks.

Use `source.patch` on exact Modules `6b290ebff828427ab66ef9c4ff3b24cef3627603`. For the named #836
combinations, use only the embedded alternate from `receipt.json`; apply and
reverse verified against each listed tree.

Four optimized scoped storage library arms built; 115 tests passed and one
ignored per arm. Cold and resident-warm typed OpenSnapshot return the same
messages, revision and fingerprint for JSONL and SQLite; the warm path did
not decode/hash the journal again and did not rewrite the derived catalog.

| Native snapshot comparison | Requests | Requested bytes |
| --- | ---: | ---: |
| jsonl/cold | 8 → 7 | 1998 → 1758 |
| jsonl/warm | 8 → 7 | 1998 → 1758 |
| sqlite/cold | 8 → 7 | 2089 → 1849 |
| sqlite/warm | 8 → 7 | 2089 → 1849 |
Counts cover only each reached comparison expression, not the whole snapshot,
application memory or Desktop startup.
