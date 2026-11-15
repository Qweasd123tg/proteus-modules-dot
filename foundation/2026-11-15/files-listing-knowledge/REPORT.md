# Files listing knowledge: failed read is not absence

2026-11-15. **Source-only candidate, not compiled or runtime-verified.**
No Rust, native UI, extension process, HTTP/API, file operation or upstream
production change was executed. The package contains an isolated source copy.

## Versions and deduplication

- Extensions main: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
- Desktop main: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Delivery main: `a78939f9804b23c851028f67d5599c5a25248364`, through PR144.
- This is a bounded repair proposal for the **existing PR85 files-recovery #2**,
  not a new finding. The older report and real-wire evidence are historical;
  neither is presented as a fresh run on these revisions.
- Known files-recovery #1, folded-row Expand All ancestry, is not changed or
  claimed fixed. PR144 project catalog epochs concern a different metadata layer.
- Eight source/doc files exactly match their pinned Extensions Git blob hashes.

## Common cause across the tree model

The read loader returns `Result<Listing>`, but `listing()` uses `.ok()` and
memoizes every failed attempt as `None`. No classification of that error proves
that a directory disappeared. Nevertheless the current tree consumes this same
`None` as absence in three places:

1. `visit` removes the directory from `expanded` after an unsuccessful read.
2. `prune` removes expanded descendants when their parent is cached as `None`.
3. `exists` returns false for children of that failed parent; `Files::panel`
   can consequently clear the user's selected path.

Partial invalidation then retains collapsed entries, including their failed
cache values. Once failure has removed the expansion intent, ordinary polling
can stop requesting the directory. The original PR85 report demonstrated that
sticky recovery behavior; this pass revalidated the current source chain only.

The existing comments already state the appropriate narrower contracts:
`prune` drops folders missing from a **complete parent listing**, and `exists`
accepts a path when its parent is **unknown**. Successful truncated listings
already use that conservative behavior. The proposal aligns failed reads with
the same absence-of-evidence rule rather than adding a new state framework.

Baseline source anchors:

- `packages/files/src/tree.rs:98–100, 118–140`: cache meaning/invalidation/loader.
- `tree.rs:187–190, 336–361`: visit, pruning and existence consumers.
- `tree.rs:218–264`: LOOKAHEAD accounting and explicit-expand retry.
- `packages/files/src/main.rs:157–193`: periodic refresh and invalidation.
- `main.rs:211–230`: read-only listing adapter and selected-path cleanup.

## Minimal candidate and invariant

`files-listing-knowledge.patch` changes production `tree.rs` by **+4/−6 lines**,
and adds **6 proposed tests / 151 lines** to its existing `tree_tests.rs`.

The common invariant is: **a failed read does not establish absence or revoke
expansion intent; a complete successful parent listing can establish absence.**

- Keep `None` as a memoized failed attempt, explicitly documented as such.
- Do not remove expansion intent merely because `visit` could not load data.
- Let failed-parent cases take the existing unknown branch in `prune`/`exists`.
- On partial refresh, expire all failed attempts as well as expanded listings.
  Successful collapsed lookahead remains cached as before.

This removes three inconsistent negative-evidence decisions at their shared
data boundary. Within a render/refresh interval, `None` still prevents repeated
loads of the same path; a later refresh permits another attempt. Existing manual
expand may also clear its failed attempt. Full invalidation already clears all
cache values and remains unchanged.

No dependency, new enum, protocol field, persistence layer, error classifier,
UI widget or background framework is added. The production gain is the shared
knowledge invariant, not the two-line net reduction.

## Important remaining behavior and costs

- `exists(true)` now means **not proven absent** for failed parents, not positive
  proof that a file exists. Explicit removal/collapse and complete successful
  parent evidence retain their existing authority.
- This does not retain the last successful child listing or display a new error
  state. Child rows can still temporarily disappear while reads fail, even though
  expansion/selection intent is preserved. Error UX requires a separate contract.
- Keeping expanded paths means they remain eligible for retry. Compared with the
  broken baseline, continued outages can therefore produce more work on later
  refreshes. LOOKAHEAD still bounds **collapsed lookahead per render only**; it is
  not a total bound on reads of expanded folders, renders or the whole session.
  CHAIN and EXPAND_ALL constants/loops are unchanged. No latency/RSS claim is made.
- Repeated failure memoization is not a new backoff policy. Existing polling,
  explicit invalidation and manual expand control when another attempt is made.
- Ordinary fresh-root `load("")?` errors still propagate. A root `None` already
  cached through another route such as `expand_all("")` remains a separate hole:
  `lines` checks key presence and can still render an empty-looking root without
  returning that error. This proposal does not claim comprehensive root-error
  handling or conceal that limitation.
- Folded-row Expand All ancestor membership, authoritative descendant cleanup
  through missing intermediate parents, malformed response classification and
  preservation of previous successful snapshots are not generalized here.
- No cause of an I/O/HTTP error is inferred. In particular, this proposal does not
  treat permission/transient/transport failures as authoritative deletion.

## Validation status

**Actually checked:** pinned refs, exact source blob hashes, source inspection,
strict patch application with fuzz disabled, byte equality of both applied files,
whitespace and independent source review. Python was used only for source/hash
bookkeeping; it did not run project code or simulate the Rust tree algorithm.

**NOT RUN:** Rust compile, rustfmt, all six proposed tests, the five existing tree
tests, package tests, wire tests and native UI checks. Rust/Cargo/rustfmt are absent
in PATH; no installation or substitute runtime was attempted. No red/green result
is claimed for this candidate.

Proposed tests use the existing real Project implementation and in-memory loaders:

1. Failed expanded parent preserves its own and nested expansion intent plus
   unknown-path existence; fold/visit share one failure until partial refresh,
   then healthy data is visible again.
2. Failed collapsed lookahead expires at refresh, while successful collapsed data
   remains cached; no automatic expansion is introduced.
3. Failed and truncated parent evidence preserve intent, but complete successful
   omission still prunes it and makes `exists` false.
4. Recovery does not reverse an explicit user collapse.
5. Failed collapsed lookahead still respects the existing per-render LOOKAHEAD
   limit on repeated refreshes.
6. Full-refresh failure preserves expansion intent and can recover on a later
   partial refresh.

Future applicable gate from upstream AGENTS: `cargo test --locked -p extension-files`,
followed by package/wire/native validation as appropriate before claiming a
verified production fix. The old report's wire observations are not a substitute
for running this final candidate.
