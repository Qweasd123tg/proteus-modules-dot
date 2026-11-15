# Independent source review

Independent design, exact-diff, composition-artifact and final-prose reviews found no source blocker for this bounded proposal. The reviewer edited no files and executed no project code or tests.

Final reviewed patch SHA256: `c98ae6e89619435180ebdac1040fdd0266a296f9a83a94e23cf5b898c718aed5`.

## Design and code

- The existing parents iterator proceeds toward the root; selecting ancestors within the recorded head includes that head and stops before its parent.
- Root/plain targets without a head retain their behavior. The new step does not list anything, and the existing deepest-start BFS/counters are unchanged.
- Disjoint `heads`/`expanded` borrows, iterator use and existing imports appear source-consistent. This is not a compile result.
- Ordinary collapse handles the added chain membership. collapse_all's narrower subtree scope remains deliberately unchanged.
- Stale heads are last-render intent, not current structure evidence. Extra expanded ancestors can increase later refresh work beyond collapsed LOOKAHEAD behavior. The full ancestry-vector cost is disclosed.

## Proposed controls and composition

The six tests correspond to the source change. Width counts the target plus 255 children at the current limit; depth retains CHAIN + 1 zero-based visits. The stale-head test asserts pruning only the missing head, not every retained descendant. The collapse test does not claim universal collapse symmetry.

The initial exact review accepted production and test logic at patch `a79cd91cd317c25b969404126b9ab0896f86c0e3cbf29bbdc69fd54f96da3831`. Its shared-EOF test hunk then conflicted with PR145. Only test placement changed in the final patch. Production SHA256 remained `3eaae5bf6636563473fab74d48dcda600c924c2a9316350ae503ef2feedb9361`.

The reviewer confirmed the final patch hash and read both final composition copies: the eight target source files are byte-identical. This does not assert equality of all directory contents; patch tooling may leave `.orig` files. The log preserves initial failures and final successes. Seventeen test names mean five baseline plus six PR145 plus six here, not seventeen passing tests.

## Final scope review

The pre-existing maximal-fold mismatch (CHAIN child edges versus CHAIN marked folders in ordinary expand) is explicitly separated from the small-chain comparison. It is not presented as fixed. Full error recovery, arbitrary descendant cleanup, native redraw and performance guarantees remain outside the claim.

Reviewed document SHA256:

- REPORT.md: `b6432af1dcefc78a52a8f7e8716f00ad468caefef892f9cf4872ca381c458d29`
- README.md: `5eebab8ecb6ac9e62ed7aed5fa324a83acb37b181d406213cd7ea60b13dc6a60`
- DESIGN-DECISION.md: `f2ff7b5e31944cc47012d17f910fb1c1a40714abd3195d82fbd4692e6bf6ab7f`

All six added Rust tests and existing tests are NOT COMPILED / NOT RUN. No wire/native recovery or runtime composition was validated. The recommendation is a source-only candidate for a known finding, not production qualification.
