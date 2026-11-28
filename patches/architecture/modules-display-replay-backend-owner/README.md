# Let storage kind own display replay

The display service retains its fold, staging, limits, and pinned-end handling.
Engine-specific replay selects the existing read path and supplies byte extent
only for JSONL, never SQLite's row count. It preserves initialization per attempt
and the original verification and fallback order.

Use source.patch on pinned Modules, where BackendKind lives in service.rs,
or source-after-stack.patch on the cumulative backend owner. Tests use local
synthetic journals. Linux checks both engines, not the non-Unix fallback.
