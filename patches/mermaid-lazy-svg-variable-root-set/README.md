# Mermaid: allocate SVG variable cycle sets only on descent

An omitted or explicitly undefined cycle path stands for the empty root.
Skip its Set construction and membership check. When a variable resolves,
the existing recursive call still owns a fresh Set of the names on that
branch, including the new name. Depth and cycle errors, raw value and
fallback lookup order, and explicit caller-provided third arguments stay
the same. The exported function still takes two required arguments; in
particular, explicit null is not an alias for omission.

One `source.patch` applies on exact Extensions
`923077d3967ae7063a6556bc378c09f97abc2854` and after
#475 → #480 → #482 → #489 → #494 → #497 → #504 (the
composed #497 and #504 variants). Only `svg-theme.mjs` changes. Git
and GNU patch forward/reverse verified both exact closures, at zero fuzz.

## Verification

- The shipped Node suite passed 12/12 in each of four arms using the same
  vendored Pele 1.12.0. Ten real renders across two themes, 15 worker JSONL
  replies, and 11 deterministic stdin layouts per tier matched exactly.
- The direct resolver passed 29 controls in each arm: results and errors,
  repeated branches, nested fallback, exact depth 32/33, explicit null
  and false, supplied Set ownership, custom accessor/method/iterator order
  and public arity.
- Source counters in test-only copies of the real worker recorded
  389 → 0 empty root Set constructor calls for a 76-node flowchart
  (47,317-byte SVG), with 615 recursive Set calls unchanged. The short
  flowchart, sequence and pie controls removed 24, 30 and 20 root
  constructions respectively without changing recursive counts. Each
  instrumented reply matched unmodified worker bytes.
- Those are constructor-call counts, not heap allocations measured by V8,
  timing, PSS or native/installed qualification. No toolkit install or
  external runtime data.
