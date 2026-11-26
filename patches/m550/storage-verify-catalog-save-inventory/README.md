# Verify durable catalog blob inventory without building a second owned map

When storage publishes a derived catalog, it already has the expected blob
inventory. The second, fresh filesystem walk now reuses the existing borrowed
inventory verifier rather than constructing another complete owned map just to
compare it. The fresh observations, original stamp checks, limits, output bytes
and atomic publication stay in place. The verifier still has bounded scratch;
this is not a result about I/O count, elapsed time, or peak RAM.

Apply `source.patch` on Modules commit `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`. If exact #815 is already
applied (tree `5e0705b3d4579425435dc7a4cbda683dde6e293d`), extract the alternative from the
receipt and apply it instead. Do not apply both.

```sh
jq -r '.selection.after_815.patch_base64' receipt.json | base64 -d > source-after-815.patch
```

The pinned storage-library suites ran serially: stock 104, standalone 105,
and with #815 107 passed, one existing ignored in each. Both candidate
variants also passed the targeted test on a real blob-backed JSONL fixture.
A stable inventory recreates the exact same catalog bytes; rewritten,
missing or invalid blob paths leave the previous catalog and the journal
unchanged. This was not a full application or end-to-end performance run.
