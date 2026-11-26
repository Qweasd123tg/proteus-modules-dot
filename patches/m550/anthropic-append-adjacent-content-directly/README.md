# Append adjacent Anthropic content directly

Ordinary messages with the same effective wire role already merge into one
Anthropic message. Render their content directly into the existing JSON
array instead of allocating and extending from a temporary vector. A new
role still gets its own array, empty content emits no message, and historical
pending results still flush at the original boundaries.

Apply `source.patch` to Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`.
If #833 already applies, use the exact alternate instead (not both).
Historical #694 is already in the pinned upstream; do not reapply it.

```sh
jq -r '.selection.after_833.patch_base64' receipt.json | base64 -d > source-after-833.patch
```

Unmasked optimized libraries built for standalone stock and candidate, and
for #833 with and without this change. All four passed 10 focused native
renderer tests. Allocation/reallocation requests on 64 adjacent same-role plain text messages
went from 400 to 337 standalone and from 400 to 337 after #833;
alternating controls were unchanged. Byte counts in the receipt are
aggregate allocation requests, not process RAM or timing.
No model, provider transport, or tool ran.
