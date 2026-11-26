# Modules: skip duplicate WriteCache validation in the built-in worker

For an admitted WriteCache call, the built-in worker now counts the JSON value against its byte budget once instead of twice. The concrete storage service still validates the typed request before taking its state lock or doing I/O. The SDK's outer method authority, other operation and feature gates, 64 MiB value limit, source checks, cache format, write path and reply are unchanged.

The actual stock and candidate workers passed the same three process tests. The cache case runs for JSONL and SQLite and checks response shape, saved cache bytes, ETags, invalid request precedence and stale-source handling. A separate four-arm check at a private 128 MiB frame setting accepted an exact 64 MiB value to the stale-source guard (no file written) and rejected one more byte under the same value policy. This is correctness and one fewer validation traversal, not measured startup speed or RAM.

Apply only `source.patch` to the exact Modules owner/tree and file preimages in `receipt.json`. Verify `SHA256SUMS` first. No alternate, other repo changes, or tested cumulative build.
