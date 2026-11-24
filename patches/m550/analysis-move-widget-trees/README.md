# Analysis: move owned widgets through the page layout instead of cloning them

Analysis used local row and column builders that reserialized already owned
children, plus the card, split and fill wrappers did the same. Reuse the
SDK's move-based row/column/fill and insert the two other child arrays as
owned values. The card's title-before-children order and split's integer
widths and key order remain as before. Ordinary panel content, selected step,
actions, scopes, error fallback, SDK and all protocol/data limits are unchanged.

**Base:** exact 151-file Extensions M384 native Cargo archive. All 151 local
M380 plus published #623 bytes and modes independently match the archive.
Two source files, one coherent ownership change in Analysis. No manifests,
lock or dependency changes. Prior disclosure-height and SDK fallback
optimizations are untouched.

**Verified:** all 19 existing native Analysis tests in each arm, plus a
paired native allocation witness. The actual Analysis stdio process with a
synthetic read-only loopback server emitted eight byte-identical replies
(14,936,995 bytes; SHA256
`9c1cb064c367db8c889ef0d1028c39590da366fefaf08421bb76659af4ec3106`).
The cases include a selected turn containing a large final answer and tool
output (Unicode, escaped bytes, complete tree), two action errors with
different sequences, read error, successful refresh, close/reopen without
stale content, and a separate revision-addressed content error.

The allocation witness wraps actual `Analysis::page` for the same selected
turn and step in both arms (1,991,000 bytes of primary disclosure text,
besides JSON/code widgets). It also verifies that a pre-owned child's
buffer is no longer replaced inside row/column/card, and checks the
unselected single-column page.

| Native page-construction metric | Before | After |
| --- | ---: | ---: |
| Allocation and reallocation requests | 3,006 | 780 |
| Cumulative requested bytes | 16,283,200 | 4,956,843 |
| Peak net live requested bytes inside page construction | 5,662,806 | 3,869,132 |
| Net live requested bytes at return | 2,831,438 | 2,840,078 |

The finished page in this fixture retains 8,640 extra bytes of spare
collection capacity; the old deep copies implicitly compacted capacities.
No extra disclosure-body copy persists. These are calling-thread allocator
layouts observed at operation boundaries, not process RSS/PSS, timing or
Desktop GUI startup.

**Reproduce:** Rust/Cargo 1.95.0 x86_64 Linux, loopback, verified locked vendor:

    python3 proof.py --baseline /path/Extensions-M384-native-inputs.tar.gz       --vendor /path/vendor --work /path/scratch

The proof compares exact modes and bytes, both native process outputs and
allocations, and reverses the patch over all 151 inputs. Only source.patch
is the product change.
