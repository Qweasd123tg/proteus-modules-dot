# Flatten per-tag SVG attribute scratch

Keep parsed SVG attributes as adjacent key/value entries in one array per tag
instead of allocating a separate two-element pair for every matched attribute.
The original two phases, duplicate attributes, first style/color, validation,
serialization order, renderer and wire reply stay unchanged.

Use `source.patch` on its exact owner tree in `receipt.json`. The receipt also
contains separate alternate patches for exact #789, #822 or their combination.
Choose exactly one variant by full input tree and verified preimage, not by a
successful context check. The exact separate #796 worker is also tested; its
patch is not included.

```sh
jq -r '.selection["after-789-822"].patch_base64' receipt.json | base64 -d > source-after-789-822.patch
```

On the pinned Node worker, exact output across eight stock/candidate bases
matched on eight wire replies and four direct controls each; 7 or 8 selected
stock regression tests passed in each arm (depending on the #822 base).
Actual raw vendor SVG had 24, 679 and 2,695 matched attributes for 1-, 32- and
128-node fixtures respectively. It no longer requests the corresponding
2-element pair arrays.

In five separate Node pairs on the exact #789+#822+#796 worker variant, V8
reported 18.54% less allocated heap-byte volume by paired median over batches
of 80 prepared materializations of the same 128-node SVG, lower on all five.
This is allocation traffic between GC boundaries, not live heap, process
memory, renderer throughput or a measurement of Desktop.
