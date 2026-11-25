# OpenCode: format synthetic instruction IDs directly from hex

Use slices of the exact existing SHA-256 hex string rather than splitting it into characters and joining each field again. Keep the same digest input, field widths, fixed version and variant digits, and UUID bytes. Instruction selection, de-duplication, projection and validation stay unchanged.

Twenty-three local synthetic-instruction controls matched through the actual OpenCode prompt hook with inert SDK boundaries. Twelve ordinary nested-file instruction records emitted 24 identical IDs. The separate probe counted 24 character arrays, 120 field arrays and 120 joins before; none of those intermediate operations remained. Deterministic IDs and output bytes were unchanged.

These are structural source-level observations, not runtime memory or speed. Use source.patch for the current file or the exact alternate below if #755 is applied. Do not apply both:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
