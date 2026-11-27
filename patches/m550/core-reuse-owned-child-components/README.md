# Reuse the owned child components map

When normalizing inline configurations, the child components value has
already been removed from the owning object. Move the map into the existing
inheritance logic instead of cloning it. The remove/reinsert order, local
overrides, inheritance, missing and malformed cases are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 92 targeted release tests on each arm.
A small synthetic inline child with its own component map saves
27 allocation requests / 2,300 cumulative bytes.
A 12-child large-payload test saves 324 requests /
420,432 bytes. The root and missing-map controls were unchanged.
Ordered normalized JSON and scoped CPU comparisons include exact static
Codex and Codex Task profiles (no processes started). Strict coexistence with
Core Dot #916–921 verified. No whole startup or process memory estimate.
