# Mermaid: collect SVG attribute matches directly

The SVG materializer already needs an ordered list of decoded attribute pairs.
Build that list directly from the same `matchAll` iterator, without first
collecting all the regex match results and mapping that temporary array.

The regex, capture reads, entity decoding, order (including duplicate names),
style/alias precedence, output escaping, errors, worker protocol and resource
limits are unchanged. The patch changes only
`packages/mermaid-render/svg-theme.mjs` at Extensions
`923077d3967ae7063a6556bc378c09f97abc2854`. It applies standalone and on the
selected #475 → #480 → #482 composition in that order; both directions
reproduced the exact pre/post images with zero fuzz.

## Verification

- The exact shipped worker tests passed 12/12 in each of four arms: stock,
  candidate, selected stock, and selected candidate, on the same Node and the
  exact in-tree Pele 1.12.0.
- Seven exact valid SVG cases (including duplicate names, zero matches,
  spacing and quote syntax), eight exact errors, and seven escape controls
  agreed across all four arms. Ten real Pele renders across two themes and
  fifteen complete worker JSONL success/error replies were byte-identical.
- On a real 76-node synthetic-input Pele flowchart (49,028 raw SVG bytes;
  47,317 after materialization), source-only counters saw the same 674
  opening tags, 1,963 regex hits and 1,963 retained attribute pairs. Both
  candidate arms removed 674 intermediate match collections. Individual
  regex match objects and the required decoded pairs still exist.
- A separate direct formatter control supplied an 856,901-byte synthetic SVG
  with 6,500 child tags; all four arms emitted the same 538,401 bytes. This
  control does not exercise or relax the worker's limits.

These are correctness and structural-work results, not CPU, latency, heap,
RSS/PSS, native GUI or whole-package Rust measurements.
