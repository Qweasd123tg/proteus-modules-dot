# Settings restore: skip decoding plain TOML strings a second time

The settings archive restore utility already parses each complete TOML document before relocating paths, and parses the result again to verify that only the intended changes were made. Between those checks it also invokes the TOML parser for every quoted fragment, even when a fragment is just printable ASCII between a single pair of delimiters.

Use the interior of an already matched, single-line printable ASCII token when it contains no backslash and does not start with triple quotes. Escapes, multiline forms, non-ASCII and control characters still use the old parser. Whole-document validation, credential checks, path relocation, archive handling and writes are unchanged.

The paired synthetic archive restored the same six files and backups. Separate per-token TOML parses fell from 79 to 12; the other 14 TOML parses were unchanged. The current 12 settings migration tests pass on both sides. This is the explicit `restore` operation, not export or normal launch. No application latency or memory claim.

Apply `source.patch` to the exact Desktop owner base in `receipt.json`. No alternate is needed; the owner already includes the distinct #729 and #731 changes.
