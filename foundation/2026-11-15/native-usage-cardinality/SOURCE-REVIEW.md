# Independent exact source review: native usage cardinality

## Verdict

No source-level blocker found. The exact candidate implements the previously reviewed F4 robustness contract without changing lifecycle classification or historical files. Suitable for the proposed bounded synthetic controls, not yet runtime-verified here. No project imports, tests, compilation, native CLI or model/API execution performed by this reviewer.

Own diff confirms before/ is byte-identical to the reviewed PR127 after tree (Core+126+127). It is not an unmodified-Core standalone patch. Seven base Git blobs and inert apply equality are coordinator evidence.

## Accounting semantics

Pi and Codex retain their original observed dict-valued native_usage lists, but pass independently counted observed completed-message/turn cardinality to usage_evidence. A missing entire usage block therefore no longer disappears from the full-total eligibility check. expected_rows must be an exact positive int; strict totals additionally require observed-row length and qualifying category contribution count to equal it. Empty observations remain None, while an observed zero retains numeric zero and positive coverage.

Per-row tuple mapping for Pi input is correct: input/cacheRead/cacheWrite must all be exact ints in the same row before their combined contribution enters values. Disjoint partial components do not become a fabricated full input row. Individual component mappings remain available as separate partial evidence. For complete valid integer rows the result equals the old sum-of-complete-column-totals. Bool/float/string/None do not qualify; negative ints retain the old policy. Lower-bound wording is consequently restricted to legitimate nonnegative counters.

The wrapper sum_usage(rows,mapping) delegates with len(rows), preserving old list-of-dict/string-mapping full-total values, including empty/unknown/zero/negative controls. OpenCode still exposes only the returned totals, not a new expected-event completeness guarantee. Extra temporary dictionaries/values allocations are real; no optimization claim is warranted.

No usage or model/tool/lifecycle extraction elsewhere changes. PR127 outcome remains independent; completed generation can coexist with unknown usage totals. PR126 receives partial_reported_usage_sums and does not turn them back into full totals. Category coverage fields are new metric evidence, not an estimate of invisible requests, lost completion events or auxiliary usage absent from this stream. No normal pinned-Pi missing-usage incidence is established.

## Tests and execution scope

Seven proposed methods are source-consistent: two whole-row red controls, complete values/raw rows, absent/null/non-dict/empty/zero, composite same-row and invalid components, wrapper compatibility, and short/long projection preserving partial evidence. Both red controls first assert input total is None; baseline returns 110 there, before any newly added field/helper access. This supports behavioral baseline controls rather than import/schema failures, provided only the new test module is added to baseline production.

The test fixture exercises Pi and Codex metrics from synthetic local stdout files. Missing blocks are deliberately robustness inputs, not claims of ordinary protocol output. Report fixture explicitly supplies successful lifecycle while retaining missing usage, correctly demonstrating the two independent axes. Short/long summary observed sums match for that identical selected set; unchanged fixture bytes are asserted.

Imports and called paths are the previously reviewed stdlib/sibling reporting and adapter paths. Test code does not invoke adapter preparation, native CLI, runner main, graders, APIs or package installation. This is source call-path assessment, not network-capture evidence. Seven candidate tests and prior 9+6 regression targets have NOT RUN at this stage. No exhaustive malformed-row/mapping validator or generator compatibility claim is made.

README states expected-row scope, missing-event and auxiliary limits, negative-int policy, wrapper scope and no historical recomputation accurately. F4 is addressed only at the observed Pi/Codex completion-to-usage projection boundary, not all native accounting.

## Own SHA256

- native-usage-on-pr127.patch: bc59d34fd938485e8a9831c87d3c6e30a4e36b01814c52f37e538d4a40cc91ef
- adapters.py: b9bf1fdcc5b8887924f3c11f3a4e9f6257243b234c9a3a2b96a1985bd3e89927
- native_usage_test.py: e986352c9cdc915102f3d9e1be337fbd63916a95906a127626267c5c24a7b763
- README.md: fbac154cffe05e0da9f937824470d7f4602cfad7d85805e2eeb56e1b3093d6d3

No production integration, publication, historical score rewrite or unrelated subsystem review performed.

## Final documentation-only revision

Read the revised sentence: one row with reported zero gives partial 0/count 1. This correctly avoids implying coverage stays one for multiple zero-valued rows. Own final patch/README hashes are updated above; adapters.py and native_usage_test.py hashes remain identical. No blocker introduced. Final inert apply equality is coordinator evidence; runtime remains NOT RUN at this stage.
