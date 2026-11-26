# Count message metadata bytes without building a JSON string

Use the existing compact-JSON counting writer for message-envelope
metadata in coding-workflow. Metadata remains a serde_json Value.
The byte count, categories, rounding, and opaque-checkpoint rules
are unchanged; this does not change how messages are persisted or
sent.

Applies to Modules f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
Both exact trees built as optimized libraries and passed 11 focused
offline tests per arm. One prebuilt 50,000-message synthetic request,
mostly null metadata with escaping, Unicode, numeric, and large-text
controls, gave the same estimate. Within message-envelope counting,
the test allocator saw 50,006 alloc/realloc requests and 572,287
cumulative requested bytes before, and zero after. These are
allocation requests, not process memory or elapsed time.
