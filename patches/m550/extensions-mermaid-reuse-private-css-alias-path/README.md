# Mermaid SVG: reuse the private alias path during resolution

When resolving nested CSS variables for a rendered diagram, reuse the private alias path rather than copying the full set for each nested reference. A caller's set is left untouched. Name, cycle, nesting, and fallback checks still run in their previous order.

The change is in SVG materialization. It is separate from the earlier reuse of SVG tag scopes and does not affect cached diagrams. The receipt records the source identities and bounded tests; there is no application timing or memory measurement.
