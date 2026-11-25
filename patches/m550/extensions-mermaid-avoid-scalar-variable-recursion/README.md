# Mermaid: resolve plain outer SVG variable values without recursion

Use the trimmed primitive string directly only for an outermost variable whose value contains no further `var(` reference. Keep the original syntax, name, lookup, fallback and missing-value checks. Nested values and explicitly supplied cycle-tracking state still take the original recursive path and preserve the depth and cycle limits.

Across eight ordinary charts rendered through the bundled Pele worker, the existing code reached 65 qualifying resolutions. The patch avoids one recursive call, a one-element array and a Set each time. An outer value with a nested reference adds one marker search before taking the original recursive path. These are structural counts, not a wall-time or memory measurement.

Apply `source.patch` to the pinned Extensions file, or choose the exact alternate from `receipt.json` if #736/#754/#769 are already applied. Do not apply both:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
