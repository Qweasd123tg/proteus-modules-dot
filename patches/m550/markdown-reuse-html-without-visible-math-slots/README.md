# Markdown: reuse compiled HTML when all math slots are hidden

Unreferenced footnotes can contain math that the parser detects but the HTML
compiler never emits. Delay allocating the rewrite buffer until a valid visible
slot is reached. When no slot survives, leave the original HTML in place and
preserve the existing empty `inlines` field.

The protected, isolated R3 build and native gate both exited 0. The native gate
compared 114 complete serialized renderer outputs and separately measured 72
real ordered JSON assignment arms. The two large hidden-only inputs removed
287,511 and 400,011 requested bytes from the late rewrite peak and gross,
respectively: the compiled HTML length plus one independently measured four-byte
key allocation. The empty-HTML control removed only the key request. Whole
render requested heap peak and retained bytes were unchanged on all 19 inputs.
This is not a worker, application, timing or PSS benchmark.

The original R3 wrapper still reports exit 1: its substring counter also counts
`API ` in its own expected PASS trailer. The separate offline typed readback
verified 18 actual API rows, 19 renderer rows, 76 measured renderer ledgers, one
unique trailer and 37 complete canonical JSON objects, then rechecked the
allocation equations against those exact immutable outputs. The wrapper and
its disposition were not changed or rerun. The earlier R2 gate remains HOLD.

One production leaf. In the verified owner source, apply merged delivery
patches #649 then #661 before this patch. Exact forward/inverse compatibility
was checked on the owner extension main and the actual Desktop extension pin;
the standalone patch was rejected.
