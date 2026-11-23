# Mermaid: search stdin chunks for LF directly

Use numeric `Buffer.indexOf(10, start)` to find the next LF. Continue from the
existing `end + 1` cursor, or leave a no-LF suffix to the existing tail path.
Searches are monotone. No byte limit, reply/reset ordering, UTF-8 decoding,
EOF handling, CR treatment, worker option, or #497 behavior changes.

This is one logical patch with two mutually exclusive source files. Use
`source.patch` on exact Extensions `923077d3967ae7063a6556bc378c09f97abc2854`;
use `composed.patch` after #475 → #480 → #482 → #489 → #494 → #497 (the
composed #497 variant). The surrounding framing code is different, so do not
apply both. Both directions were checked with Git and exact GNU patch
forward/reverse byte readback at zero fuzz.

## Verification

- The shipped Node suite passed 12/12 in each of four arms with the same
  vendored Pele 1.12.0. The existing 11 deterministic input layouts per pair
  preserved exact stdout bytes, stderr and exit, including cap, split UTF-8,
  coalescing and EOF. Ten real Pele renders across two themes and 15 worker
  JSONL replies were also byte-identical across the four arms.
- Eight targeted layouts preserved wire bytes and ran the actual loop with
  test-only source counters. For a 3,732-byte synthetic Unicode diagram
  request plus LF, the stock loop ran 3,733 JavaScript byte checks. The new
  loop made one numeric search (two when the LF was in its own chunk) across
  the same logical span in either tier. Empty chunks, no-LF tails, sibling
  frames, a dense blank-line run and small valid frames are separate controls.
- Node v24.22.3 routes numeric Buffer search to native forward `memchr`.
  These counts are source operations, not physical byte loads or a speedup
  claim. Dense LF runs can pay one call per byte. No timing, memory,
  native Desktop or installed portable verification was performed.
