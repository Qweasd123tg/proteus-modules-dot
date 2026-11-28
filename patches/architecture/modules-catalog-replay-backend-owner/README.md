# Let storage kind pick the cold catalog reader

The catalog owns its fold and no longer imports the concrete journal readers.
Move dispatch and the replay hint to the existing BackendKind owner. Preserve
one verified JSONL replay, SQLite's special transaction, and catalog validation
and publication ordering. The public API and journal bytes are unchanged.

Use source.patch on pinned Modules, where BackendKind lives in service.rs, or
source-after-stack.patch on the cumulative tree with the existing backend
owner. The focused native tests use synthetic local session stores.
