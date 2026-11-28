# Put writer close orchestration in the storage service

Standalone Modules patch for `7274147162cb226f05df13a52b4a271fa5619313`. Verify with `sha256sum -c SHA256SUMS`. Apply **only one** source alternative:

- `source.patch` on the exact stock commit.
- `source-after-stack.patch` on the Modules stack through #967, tree `e4fdb7e77f25600d0ec38901046459a7896fe231`.

The storage service now closes the writer it owns. The catalog captures and refreshes its advisory cache, but no longer receives the live writer or drops the backend. Closing the last token still captures a verified head, drops only the backend, checks journal and blob identity and conditionally rebinds the SQLite cache before the writer lease is released. Raw identity fields, cache formats, IPC and JSONL behavior are unchanged.

Run `git apply --check` before applying. Both patches were tested independently with offline native storage and process tests and the unchanged Core swap fixture for JSONL and SQLite. See `receipt.json` for exact trees, results and scope.
