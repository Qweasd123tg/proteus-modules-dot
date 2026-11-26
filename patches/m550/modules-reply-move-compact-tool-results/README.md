# Modules: move compact tool-result strings into storage replies

The reply adapter moves an already-owned tool output or error into its existing serialized slot if the string is at least 4 KiB and has no spare capacity. Short strings and strings with spare capacity still use the normal serializer. Absent errors stay distinct from empty errors. Other fields, record ordering, storage policy, transport and on-disk formats are unchanged.

Three tests passed in the isolated standalone Rust 1.95 build. One typed adapter test confirmed exact serialized bytes and pointer transfer only for eligible fields. Stock and standalone candidate workers also matched five normalized ordered result/error payloads per JSONL and SQLite, using seven inert storage facts. No tool or provider was called. Neither production eligibility nor speed or memory was measured.

Apply **one** variant only. Use `source.patch` on the exact Modules owner. If #803 is already applied, verify the exact preimages in `alternate.source`, then extract `alternate_scoped_patch` from `receipt.json` without appending a newline and verify its SHA-256. #804 is disjoint and can be present. The alternate was checked as source only, not built or run. #618 and #664 are already integrated.
