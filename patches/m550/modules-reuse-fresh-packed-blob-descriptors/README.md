# Modules: reuse descriptors for freshly packed JSONL blobs

After successfully writing a new packed JSONL manifest, use its own generated descriptors to list the touched chunk paths instead of parsing the serialized manifest again in memory. The manifest bytes, chunk checks, ordered paths and duplicates, and durable write order stay the same. Existing on-disk packed files still go through the original read, validation, and parse; inline, raw, public archive, and SQLite behavior are unchanged.

Exact library tests: 104 stock and 106 candidate passed, with the same pre-existing manual benchmark ignored. A separate test-only default JSONL append/leased commit witness confirmed one fewer in-memory manifest parse. It produced identical journal and manifest bytes and an identical list of ten chunk paths (four repeated occurrences). The reused-file, raw codec, damaged-chunk, operation retry, and controlled atomic-rename failure cases kept their prior results. No disk read was removed. No app RAM, timing, CPU, or standalone worker transport measurement.

Apply `source.patch` to the exact Modules owner in `receipt.json`. No alternate. The #814/#815 checks cover source application only.
