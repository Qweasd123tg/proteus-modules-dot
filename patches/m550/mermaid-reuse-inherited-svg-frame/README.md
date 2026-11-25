# Mermaid: reuse unchanged SVG inheritance frames

SVG materialization pushes one scope stack entry for each opening tag that is not self-closing. Keep the same stack depth and pop order, but reuse the parent's private frame when both the inherited variable map and resolved current color are unchanged. Any local variable write still clones the map; any real color change still gets its own frame. A scope frame never escapes materialization.

This targets fresh Mermaid diagrams rendered by the Node worker with bundled Pele, not cached renders, regular transcript loading, or application startup. The worker's input handling, limits, theme resolution and SVG output stay the same. Frame counts are logical construction counts, not measured heap/RSS/PSS or wall time. See the receipt for exact paired verification.
