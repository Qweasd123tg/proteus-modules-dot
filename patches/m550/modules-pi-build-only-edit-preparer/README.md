# Pi workflow: build only the native edit argument preparer

The pinned Pi coding SDK gives only its built-in `edit` definition a preparer. The workflow now obtains that preparer only when the selected tool is tagged with the exact existing SDK identity and named `edit`. Duplicate matching descriptors share that function within the turn. No cross-turn cache, tool selection, argument or schema validation, execution path, or approval behavior is changed.

For the stock four-tool selection, the workflow builds one definition instead of four. It builds none if no matching native `edit` was selected. Keep the same original working-directory read and use the pinned SDK's existing constructor and preparer, not another normalizer. Tests cover the exact worker/workflow with inert SDK and service seams. No real tools, installed execution, application memory, or timing measurements.

Use `source.patch` on the exact Modules owner basis. On the recorded chronological scoped basis after #742, #744, #761 and #763, use the embedded alternate from `receipt.json` instead. #735 is already present in the owner loop. Apply exactly one variant:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
