# Skip unused usage statistics on historical conversation reads

Current conversation reads already skip the separate usage projection.
Apply the same mode for older revisions and the pre-replacement view.
Model context and validation are still applied to every record in the
pinned prefix, including records after the requested point. ReadUsage,
resumption and display snapshot projection still build usage as before.

Exact Modules `6b290ebff828427ab66ef9c4ff3b24cef3627603`; for the exact #839 combination in the
receipt, use only the embedded alternate. Four unmasked optimized storage
libraries built; 115 tests passed and one ignored each. Typed history,
model context, revision, full-prefix decoding and independent usage
readback matched on JSONL and SQLite. For a 25-model-turn fixture,
the historical read no longer made the usage projection's 55 allocations/reallocations
(11986 total requested bytes) for JSONL and
55 (11986 bytes) for SQLite.
No allocations were seen in the usage projection on the zero-model-turn controls. Counts are scoped to that projection, not the whole request.
