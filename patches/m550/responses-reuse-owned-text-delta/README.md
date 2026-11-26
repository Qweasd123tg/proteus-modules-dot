# Reuse the parsed Responses text allocation

Move the parsed owned String into an ordinary delta event instead of copying
it. For refusal.done, keep suffix semantics while moving the final text into
the fallback buffer. The fallback still accumulates fragments; transitions
between content parts still use the current newline rule. No HTTP,
dispatch, event order, message identity, phase or tool handling change.

Apply to Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`; no prior selector
through #830 overlaps. Optional independent regression patch in the receipt:

```sh
jq -r '.optional_regression.patch_base64' receipt.json | base64 -d > responses-regression.patch
```

Both unmasked production libraries compiled with the pinned dependency
closure. Fifteen focused native tests passed per arm. A private observer
confirmed that normal and refusal deltas and the final refusal buffer
retain the parser's nonempty String allocation. Synthetic Go loopback
verified three ordered typed deltas, stable IDs and phase, refusal metadata,
and terminal reconstruction. No measured whole-application memory or time
gain, and no claim of an allocation-free stream.
