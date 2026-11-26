# Modules: bound scratch memory when checking large durable catalogs

After the same bounded read and typed parse, the large catalog path drops the input buffer and streams the same compact JSON into SHA-256 through a 4 KiB buffer. The small catalog path still reuses its input buffer. The file format, read and checksum bytes, source rechecks and writer behavior are unchanged.

Exact library tests: 104 passed on stock, 106 with the patch, and one pre-existing manual benchmark was ignored in each. In a separate test-only probe, 416 normal JSONL appends produced an unpadded catalog with 1,250 blob paths. Fresh List and OpenSnapshot preserved their results and file bytes; checksum scratch capacity fell from 256 KiB to 4 KiB. The large SQLite control used a copied JSONL blob inventory. This is buffer capacity just during the checksum, not a process RAM, timing, append-speed or worker transport measurement.

Apply only `source.patch` to the exact Modules file and lock in `receipt.json`. No alternate. #814 is independently source-compatible.
