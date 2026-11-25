# Mermaid: pick the first inline color in the existing style pass

The SVG materializer already walks inline style declarations to collect CSS variables. Remember the first `color` declaration during that pass instead of searching the same list again. An empty first value still blocks an attribute fallback, and the existing inheritance, variable resolution, and `currentcolor` rules remain unchanged.

In the checked eight-diagram wire fixture, this removes 270 calls to the separate search (120 callback invocations), with 104 direct comparisons inside the pre-existing style loop. The SVG bytes matched. This is a structural check of the renderer, not a measurement of time or memory.

Use `source.patch` on the exact Extensions owner basis. Use the scoped alternate embedded in `receipt.json` instead if the exact previous same-file changes #728, #736, #754, #769 and #778 are already present (do not reapply #728 if it is in your basis). The scoped widget checks include the separate worker companion #758. Choose one patch, not both. Applying an owner variant to the historical alternate context is not supported.

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
