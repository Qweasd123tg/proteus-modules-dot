# Borrow historical call IDs inside the Responses request projection

Use the identifier already owned by the canonical request as the key in
the transient call-surface map. Tool-call and result JSON are unchanged.
Result type still follows the latest preceding equal ID, never a later
call, and keeps the existing default for an unknown ID. This change is
historical rendering only and neither dispatches nor invokes tools.

Apply to Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`.
Historical #694 is already present byte-for-byte. Do not apply it again.
An optional separate regression patch is in the receipt:

```sh
jq -r '.optional_regression.patch_base64' receipt.json | base64 -d > history-key-regression.patch
```

Both unmasked production libraries compiled with the pinned closure.
Seven focused native tests passed per arm. Exact JSON comparisons
include function and freeform history, missing and repeated IDs.
For 32 distinct, nonempty historical calls, the actual transient map
reused 32 original ID buffers, compared with 0 before. These are scoped
allocation-identity observations, not whole-provider memory or timing.
