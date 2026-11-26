# Avoid copying OpenAI response IDs for lookup

Skip lookup entirely for empty identity maps. Otherwise borrow exact
string IDs; only absent or non-string IDs use the unchanged physical
output index key. Do not fall back on a failed explicit string lookup.
Streaming key ownership and parsing semantics are unchanged.

Exact Modules base: `6b290ebff828427ab66ef9c4ff3b24cef3627603`. Strict indexed apply/reverse
verified for the single response.rs source delta. Both optimized
unmasked model-pack libraries built. 18 scoped
native tests passed per arm, including terminal stream cases.

For 128 response items with an explicit synthetic key per item, removes
128 temporary key allocations in both the empty-map and mapped cases.
The mapped fallback-only control was unchanged. The long diagnostic
keys make allocation traffic visible; this is not process PSS or time.
