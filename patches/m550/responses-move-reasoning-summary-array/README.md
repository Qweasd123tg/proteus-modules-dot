# Move the completed Responses reasoning summary into its JSON slot

The summary array is already built. Move it into an existing JSON slot
rather than serializing it again through the enclosing object. Whitespace
is only used to decide if the summary is blank; nonblank text is kept
verbatim. Encrypted-content string versus null, object order and input order
remain unchanged.

Apply `source.patch` to Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`.
If #832 already applies, use the exact alternate instead (not both).
Historical #694 is already in the pinned upstream; do not reapply it.

```sh
jq -r '.selection.after_832.patch_base64' receipt.json | base64 -d > source-after-832.patch
```

Unmasked optimized libraries built for standalone stock and candidate, and
for #832 with and without this change. All four passed 7 focused native
renderer tests. Allocation/reallocation requests on 32 nonblank historical reasoning summaries
went from 1712 to 1552 standalone and from 1712 to 1552 after #832;
blank controls were unchanged. Byte counts in the receipt are
aggregate allocation requests, not process RAM or timing.
No model, provider transport, or tool ran.
