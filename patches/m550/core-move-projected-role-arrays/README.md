# Move already projected configuration role arrays

Core moves the completed role array into its output JSON value instead of
serializing an already-owned tree back into a second tree at every inline
level. Selected fields, nulls, malformed entries, nesting and order are
unchanged. No persistent/runtime schema or selection logic changes.

**Choose one patch** on the exact Core commit `7f86a85b0b45de62c08ca36f21244afc03e6101e`:
- Unmodified Core: `git apply --check source.patch && git apply source.patch`.
- Exact tree after applying Dot #916 and #917:
  `git apply --check after-dot917.patch && git apply after-dot917.patch`.
  Its base is `54519f45df2df75e5cacec4beecbdfa3d99b929c`.
Do not stack these alternatives. Forward and reverse tree checks passed.

92 targeted release tests passed on each of stock, standalone and
combined. All synthetic outputs matched exact ordered JSON bytes.
Standalone eliminates 13 allocation requests and 1,184
cumulative requested bytes on one synthetic inline level. The depth-eight
mixed case saves 1224 requests / 96,280 B.
Only local projection was isolated for these figures, not launch or total PSS.
