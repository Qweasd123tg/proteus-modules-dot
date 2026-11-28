# Desktop: give wire colors an independent owner

Graphs, trees, lanes and presentations can now use the common wire color type without importing the top-level widget schema that embeds them. Move the wire `Tone` type, its deserializer, and the six-digit RGB parser unchanged. This is distinct from mapping those values to the active native theme. Schema, JSON, visuals, extension installation and protocol are unchanged.

Use `source.patch` on Proteus-harness/Proteus-desktop at `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Use `source-after-stack.patch` instead on the verified cumulative Desktop tree; it preserves earlier renderer changes. See `receipt.json` for exact bases and native verification.
