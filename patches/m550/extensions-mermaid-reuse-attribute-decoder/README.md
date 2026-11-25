# Mermaid: reuse the SVG attribute decoder objects

Reuse the existing regular expression, pure replacement callback and five named-entity mappings across SVG attributes. Match patterns, one-pass decoding, escaping, style handling, validation and rendering stay unchanged.

Eight ordinary charts with pinned Pele produced byte-identical results in direct rendering and through the worker. They exercised 1,001 attribute decoder calls. The probe observed 1,001 distinct regular-expression and callback objects before and one of each after. Recognized attribute entity matches stayed at 28: the lookup table changed from per-match to shared. Six stock positive tests per arm also passed. Counts are identities under instrumentation, not V8 allocation, runtime or application memory measurements.

Apply source.patch for the pinned current file, or extract the exact alternate for the cumulative #736/#754 SVG base (not both):

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
