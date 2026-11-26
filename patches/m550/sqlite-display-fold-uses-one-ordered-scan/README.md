# Fold the SQLite display snapshot with one ordered scan

On the normal writer schema, a single read transaction captures and hashes
the complete pinned prefix while strictly validating records and building
the existing private page stage. The preliminary BLOB scan goes away.
Custom or empty sources use the old path. Any malformed or unusual prefix
discards the speculative stage and runs the old checks on the same pinned
transaction, preserving legacy acceptance and error precedence. The format,
byte budgets, page identities and catalog publication checks are unchanged.

Apply `source.patch` to exact Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`.
If exact JSONL patch #828 is already applied, use the separately tested
alternate from the receipt instead; do not apply both.

```sh
jq -r '.selection.after_828.patch_base64' receipt.json | base64 -d > source-after-828.patch
```

Native pinned SQLite storage results: 107 passed in each base, 109 passed
in each candidate including two extra transaction/stage controls; one
existing ignored per arm. On the actual display service, 20 synthetic
records contributed 1,213,222 B; separate preliminary hash input went
from that amount to zero, with the same 20 strict decodes, digest and
visible page. Tests also cover a WAL append while the read is pinned,
the middle digest boundary, empty/custom schema, unusual rows and
preserved BLOB-type error precedence. These are logical payload counts,
not physical disk I/O, latency or process memory measurements.
