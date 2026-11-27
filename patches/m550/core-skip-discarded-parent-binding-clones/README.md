# Avoid cloning parent binding maps only to replace them

Child scope initialization keeps the inherited catalogue and selected alias
but leaves local binding maps empty until capture. Normal model inheritance
still consults the original parent, and its checks and the legacy independent
route do not change.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`; 92 targeted release tests per arm.
A nested two-role synthetic profile saves 84 requests /
9,882 cumulative bytes. A twelve-role large-settings stress
profile saves 384 requests / 1,284,852 bytes.
Root and no-binding controls unchanged in allocation accounting.
Output hashes, ordered JSON, and binding conflict behavior match.
Strict coexistence with #916–919 checked. No startup or PSS claim.
