# Expand All preserves the whole known folded row

## Status

**Source-only candidate for existing PR85 files-recovery #1. Not compiled or runtime-tested; not a new finding.** No upstream or live data changed. No file operation, HTTP, extension process, native UI or project test ran. Rust/Cargo/rustfmt are unavailable; no replacement implementation was run as behavioral evidence.

Target Extensions: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`. Delivery/dedup baseline through #151: `e89a3176bc726451a31c276a3738ccb53b0b30c7`. Eight source/doc copies match the pinned Git tree (`SOURCE-BLOBS.tsv`). The earlier PR85 report's real-wire observations are historical evidence, not a test of this patch. PR145's uncompiled failed-listing proposal is a separate part of the same tree family.

## Invariant and current consequence

The tree represents a single-child folder chain as one logical row. `Line.path` is its deepest folder, while `Project.heads` records its first folder. In the pinned `packages/files/src/tree.rs`:

- `fold` (218-240) creates that representation and head mapping.
- Ordinary `expand` (242-264) uses the head and records chain folders in `expanded`, subject to its existing CHAIN loop.
- `expand_all` (290-314) instead starts at the deepest path and records only that path and its descendants.
- Partial `invalidate(false)` (118-129) expires only expanded listings in the baseline. Therefore the missed folded ancestors can remain stale lookahead data.

The known example is `src/lib/existing.rs`: Expand All on the displayed `src/lib` opens the descendant but leaves `src` outside the refresh set. A newly added `src/new.rs` can remain hidden by the old cached fold. PR85 demonstrated the old source's real-wire behavior; this pass confirms the current source chain only.

The narrower common invariant is: **expanding a known folded row records all folders represented by that row as expansion/refresh intent, regardless of whether the operation also expands descendants.** This brings Expand All toward the existing ordinary row-expansion intent, rather than repairing one later rendering symptom. It does not assert that ordinary `expand` already satisfies the invariant at every chain-length boundary.

## Minimal candidate

`folded-expand-all.patch` adds **10 production lines**, all at the start of `Project::expand_all`. If the exact row path has a recorded head, it extends `expanded` with `paths::parents(path)`, stopping when an ancestor is outside that head. Existing `paths::within` defines the boundary. There is no new state, helper framework, dependency or wire field.

The existing BFS still starts at the supplied deepest path. Its count, depth, queue, cache and loader logic are unchanged. The new membership step itself calls no loader. A plain/root path with no `heads[path]` entry behaves as before.

The alternatives deliberately avoided are significant: calling `expand` first could perform extra listings outside the Expand All counter; starting BFS at the head would spend descendant count/depth budget on the folded prefix; unrestricted `reveal` would open all ancestors even for a hidden nonfolded argument; invalidating every collapsed folder would defeat existing lazy lookahead behavior.

## Costs and precise limits

- `paths::parents` allocates the entire ancestor vector before the folded portion is selected. Its cost depends on overall path depth, not only the folded-chain length. Extra expanded entries retain the intended ancestors.
- Those ancestors now participate in later refreshes. They may bypass LOOKAHEAD as expanded folders. **Total I/O is not unchanged**, and there is no latency/RSS/performance improvement claim.
- The operation's existing BFS still visits at most `EXPAND_ALL` folders and descends through depth `CHAIN` from the deepest target (depth zero included). That is not a bound on all later renders, polls or total expanded entries.
- `heads` describes the last render and survives invalidation. This restores intent for that known row, not proof of the current filesystem shape. Subsequent successful listing/pruning remains authoritative; the patch does not add speculative ancestor loads.
- Ordinary `collapse(path)` already removes the corresponding folded chain. `collapse_all(deepest)` retains its existing subtree-only scope and can leave folded ancestors expanded, just as it does after ordinary `expand`. Symmetry of all collapse variants is not claimed.
- The separate maximal-fold boundary is untouched: `fold` can follow CHAIN child edges while ordinary `expand` marks at most CHAIN folders. The new small-chain comparison test does not assert universal equivalence of those operations or repair that existing boundary.
- Failed-read classification, last-good listing retention, root `None` error caching, malformed-listing behavior and complete cleanup through absent intermediate parents are not fixed. In particular, this is not a substitute for PR145 and does not claim comprehensive tree recovery.

## Six proposed tests, all NOT COMPILED / NOT RUN

The patch adds 162 lines to the existing tree test module, using the actual Project type and in-memory Listing loaders:

1. New siblings in two folded ancestors become present in returned lines after both partial and full refresh, with one load per ancestor in that render.
2. Ordinary Expand and Expand All have matching known-chain intent; ordinary collapse clears it, while the unchanged collapse_all asymmetry is explicit.
3. A root and a nonfolded hidden target preserve existing ancestry behavior.
4. A retained head after cache invalidation requires only the original deepest target's direct load; later complete parent evidence removes the missing head. This does not assert removal of every stale descendant.
5. Folded ancestry neither consumes nor expands the existing width/listing budget: deepest target plus 255 children at the current limit.
6. Folded ancestry neither consumes nor expands descendant depth: `CHAIN + 1` visits with zero-based depth.

The width/depth fixtures seed the existing private head map directly to isolate bookkeeping from native rendering. These are proposed source regressions, not executed observations. The five existing tree tests were not rerun, and the tests do not demonstrate wire polling or native visible recovery.

## Actual text checks and composition

Forward and reverse whitespace apply checks succeeded. Zero-fuzz application to a fresh isolated source copy produced candidate-identical bytes for all eight inspected files. No project executable was involved.

The first test patch appended at the same EOF as PR145 and correctly failed composition in both orders. The final candidate changes only the placement of its six tests, inserting them before the first baseline test. Production and test logic were unchanged by that correction. Initial failure logs are preserved in `INITIAL-COMPOSITION-CHECKS.json`.

The final patch and PR145 now apply with zero fuzz in both orders, producing byte-identical composed files. Expected line offsets occur when applying PR145 after this patch and are recorded, not described as zero offsets. The composed test source has 17 unique test functions: five baseline, six PR145, six here. **None ran.** `SOURCE-TEXT-CHECKS.json` records the exact logs and hashes. PR145 is not a prerequisite for applying this patch; successful text composition is not a compile or runtime compatibility guarantee.

Independent design and exact-diff review found no source blocker; final hashes and scope review are recorded in `INDEPENDENT-REVIEW.md`. Before production use: format/compile with the pinned toolchain, run `cargo test --locked -p extension-files` including both candidates where applicable, then validate the actual folded-row menu, refresh/polling and collapse behavior in the normal wire/native workflow. Do not reuse the historical baseline result as a candidate pass.
