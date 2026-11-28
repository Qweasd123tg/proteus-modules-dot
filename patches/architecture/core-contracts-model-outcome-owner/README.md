# Keep passive outcome types in Domain

Domain events and usage no longer need to import Model Standard for the
outcome types. Existing flat and nested Model Standard imports still
refer to exactly the same Rust types. Event fields, spellings, token
arithmetic and missing versus explicit zero counts are unchanged.

Use source.patch on pinned Core or source-after-stack.patch on the cumulative
tree. Verification is local synthetic serialization only.
