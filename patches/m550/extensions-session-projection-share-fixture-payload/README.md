# Session projection benchmark: share immutable fixture text within each widget

Each synthetic tool-result row uses the same repeated-character string. Construct it once per nonempty fixture instead of once per row. Every row, tool dictionary, and arguments dictionary remains a separate mutable object. No cross-widget cache, admission changes, altered wire format, or changes to the snapshot's full size.

At the documented `--full` default, each widget has eight rows with 512 KiB each. The driver now holds 512 KiB instead of 4 MiB of unique fixture characters while those rows are live. All eight rows still serialize in full, and the actual default snapshot frame is unchanged at 4,195,667 bytes including its newline. This distinguishes fixture string objects from application memory, process RSS, and encoded data. Manifest mode still builds none.

Independent inert-peer runs compared both exact bases through the actual CLI: 12 paired cases per base plus direct controls. Wire bytes, redacted traces, report contents (apart from checked source fingerprints), errors, and mutable-object independence were preserved. Strict forward and reverse checks covered both patch orders.

Use `source.patch` on the pinned Extensions owner base. If #783 is already on the exact checked source, use the embedded alternative from `receipt.json` instead. Do not apply both variants:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
