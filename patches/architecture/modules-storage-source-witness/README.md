# Let storage source checks live outside the catalog cache

Standalone proposal for Modules commit `7274147162cb226f05df13a52b4a271fa5619313`. Verify this packet with `sha256sum -c SHA256SUMS`. Apply **only one** alternative in the Modules checkout:

- `source.patch` on the stock commit.
- `source-after-stack.patch` on the Modules stack through #961 (tree `7f2fdb56e21d6b2111bd2661978bd838c1e1b45e`). It keeps the PrefixCache ownership established in #945.

The writer, views and display read shared journal and blob fingerprints from the code that observes the source on disk. They no longer need catalog persistence code for those checks. The catalog keeps its cache format, encoded size limit, write policy, and SQLite close orchestration. Blob limits, path checks, empty-WAL handling, exact revision checks, and the writer lease remain unchanged. No IPC contract, storage format, or package routing changed.

Both variants are checked forward and in reverse. See `receipt.json` for the native storage and worker test groups and the independent Core-to-worker swap with synthetic JSONL and SQLite sessions. No real model or tools are used.
