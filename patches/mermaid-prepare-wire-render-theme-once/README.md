# Mermaid: prepare the validated theme once per worker render

On the worker's JSON protocol path, Pele's font options and SVG materialization
come from the same checked theme. Snapshot the fixed color and font fields,
validate them once, and reuse the resulting private map for that render. The
public direct `renderDiagram` and two-argument `materializeSvg` paths retain
their previous raw-theme validation and getter/read order. The new preparation
helper does not expose the map or an unvalidated materializer.

The worker's input and output bounds, source/error checks, render options,
text-cache cleanup and public wire format are unchanged. The snapshot and
materialization closure are scoped to a single reply; nothing is cached across
requests.

## Verification

- The exact shipped Pele worker tests passed 12/12 on each of stock, candidate,
  selected stock, and selected candidate. The selected order is #475 → #480 →
  #482 → #489 on Extensions `923077d3967ae7063a6556bc378c09f97abc2854`.
  Both patch directions reproduced the complete worker closure with zero fuzz.
- Ten real Pele renders across two themes and 15 complete JSONL replies were
  byte-identical. Eleven additional targeted theme/error replies, five direct
  accessor/read-order cases, and snapshot isolation/scoped alias controls passed.
- In four successful actual JSONL requests (including repeated theme input),
  source-only counters saw 8→4 theme-map builds and 152→76 entries written
  in each tier. The snapshot and closure are additional objects; no physical
  allocation, memory or timing result is claimed.
- Eleven deterministic input chunk layouts also matched exactly between
  pristine stock and full composition, including split UTF-8/LF, coalescing,
  CRLF, cap boundaries and EOF.

These are local vendored Node correctness and structural checks, not a native
Desktop/installed portable, Rust suite, or performance benchmark.
