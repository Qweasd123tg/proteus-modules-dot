 SQLite memory joins punctuation-separated search terms into a different token

**Confirmed functional retrieval defect, suggested P2.**

`context_provider/sqlite-memory/src/lib.rs:175-187` splits only on whitespace, then deletes other punctuation inside each item. It therefore joins code/path components that SQLite's actual index treats as separate words. A verbatim query for a newly saved fact can return no memories.

`audit_exact_saved_developer_terms_do_not_recall_after_punctuation_merging` uses the actual store `remember` and `recall` against fresh in-memory SQLite databases:

| Saved fact and exact query | Generated match expression | Exact results | Control query | Control results |
|---|---|---:|---|---:|
| `src/config.rs` | `"srcconfigrs"*` | 0 | `src config rs` | 1 |
| `Config::load` | `"Configload"*` | 0 | `Config load` | 1 |
| `v1.2.3` | `"v123"*` | 0 | `v1 2 3` | 1 |

This is independent of semantic-search quality or language-model behavior. Nothing is deleted from storage. The provider delegates directly to the same recall method (`src/provider.rs:16-22`), while automatic context recall forwards task text (`context/context-pack/src/retrieval.rs:9-14`). Both explicit memory-tool queries and automatic recall can therefore encounter this mismatch.

**Fix direction:** tokenize separators consistently with the configured FTS tokenizer; do not delete separators in a way that merges adjacent indexed words. Preserve the intended literal-query/prefix behavior and avoid exposing FTS syntax unintentionally. Include code identifiers, paths, versions and punctuation-only/empty queries in tests. The probe is store-level, not a full process-boundary test.

