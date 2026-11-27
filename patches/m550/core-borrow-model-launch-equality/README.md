# Compare model launch settings without cloning whole components

The previous conflict check cloned both component values and removed
only top-level exports before comparing. Compare borrowed key/value pairs
instead. Nested data, key order independence for equality, conflict and
shape errors, and exports validation/insertion are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 92 targeted release tests per arm.
A small same-name compatible fixture saves 42 allocation
requests and 4,153 cumulative bytes; a deliberately
large twelve-role layout saves 504 requests /
835,500 bytes. The no-inline root allocation control is unchanged.
Exact ordered output and repeat timing also compared parsed checked-in
Codex and Codex Task profiles. No providers or subprocesses invoked.
Strict coexistence with the earlier Core configuration patches #916–921 and
#923. These are normalization-only measurements, not full startup or PSS.
