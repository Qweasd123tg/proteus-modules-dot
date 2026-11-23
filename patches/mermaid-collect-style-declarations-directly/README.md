# Mermaid: collect parsed style declarations directly

Append each valid key/value pair to the final declaration list. Keep
the original split on semicolons, first-colon lookup, trimming, pair
shape, and order. An exactly empty style no longer needs to split.
Variable, attribute, theme, limits, and worker behavior are unchanged.

One `source.patch` applies to exact Extensions
`923077d3967ae7063a6556bc378c09f97abc2854` and after
#475 → #480 → #482 → #489 → #494 → #497 → #504 → #506
(use the composed variants of #497 and #504). Git and GNU patch verified
forward and reverse byte equality on both complete Node worker closures.

## Verification

- Shipped tests: 12/12 in each of four arms using the same vendored
  Pele 1.12.0. Ten real renders across two themes and 15 JSONL replies
  were byte-identical. Eleven deterministic stdin layouts per tier
  preserved exact stdout, stderr, and status.
- In each arm: 14 direct list/ownership cases including 2,048 pairs,
  six materialized CSS cases, and three exact error cases. Tests cover
  empty/whitespace strings, unusual delimiters, trimming, duplicate
  declarations, aliases, entity output, and validation precedence.
- In an actual 76-node flowchart with a 47,317-byte SVG, both tiers
  executed 690 → 0 per-segment wrapper-array sites and 674 → 77
  split sites. The 93 emitted declaration pairs were unchanged.
  Small flowchart, sequence and pie fixtures independently matched
  exact uninstrumented worker bytes.
- These are source-level counts, not V8 heap, time, process memory,
  Rust, or installed portable verification.
