# Project historical Anthropic results directly into the pending list

Return a lazy iterator for a historical Tool-role message instead of creating
a temporary list just to extend the pending list. The actual result block,
ordering, grouping, flush boundaries, image/error contents, and JSON stay
unchanged. This is historical rendering only; it never invokes a tool.

Apply to Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`.
Historical #694 is already present byte-for-byte; do not apply it again.
An optional exact regression patch is embedded in the receipt:

```sh
jq -r '.optional_regression.patch_base64' receipt.json | base64 -d > anthropic-results-regression.patch
```

Both unmasked production libraries compiled. Seven focused native tests
passed per arm, including exact grouping and JSON of mixed historical
results. On a synthetic input of 128 one-result messages, the scoped
renderer made 1,171 allocation/reallocation requests instead of 1,299 and
requested 99,511 instead of 115,895 aggregate bytes. The necessary pending
and output lists remain. These are allocation requests, not process RAM
or timing. No model or tool was invoked.
