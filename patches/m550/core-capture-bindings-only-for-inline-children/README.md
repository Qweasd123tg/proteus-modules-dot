# Capture model bindings only for inline children

The scope binding maps are read only by recursively normalized inline
children. Leaf profiles and external-only roles do not need those copies.
Catalogue, selection, inherited settings and the original validation walk
are unchanged; mixed sources still capture for their inline children.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 92 targeted release tests each, matching
configuration hashes and exact ordered output bytes. Three external roles
with synthetic transport/settings save 35 allocation
requests / 5,284 cumulative bytes. The bare and wide
no-binding controls show no allocation change. Separate CPU controls cover
wide external, first-inline and last-inline cases. Strict coexistence with
#916–920. No app startup or process memory claim.
