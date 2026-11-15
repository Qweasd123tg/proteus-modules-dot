> Publisher freshness note: original review below covers historical Modules `c0351425`. The candidate hash is unchanged; parser package/caller preimages are identical on the batch base `42ae7535`, with fresh source identities and text checks recorded in the common SOURCES/VERIFICATION. No fresh compile/test claim follows.

# Independent source review: patch parser ownership

Reviewed patch SHA256: `d98effa9726ecd52620d017a5b176dce254ffe12027f6d2074d3f926b197cf5b`.
Base: Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.

## Verdict

No blocking source-level correctness defect found in the checked production caller. This is not compile/test approval. Rust, Cargo, rustfmt and project tests were not run. Publication was not performed.

## Ownership and lifetimes

- `push_delta(&mut self, delta: &str) -> Result<&[Hunk], ParseError>` returns a slice tied to the receiver lifetime by Rust method lifetime elision, not to `delta`. The character-loop test's temporary `ch.to_string()` therefore does not need to outlive the call.
- A live preview borrow prevents mutation or consumption of the parser while that preview remains in use. The production caller discards the preview at its statement, before `finish`. The tests compare temporary slices inside a single assertion; the character-loop borrow is last used inside each iteration. No retained view across another mutable call was found.
- `finish(mut self)` moves `hunks` and `environment_id` from two distinct fields. Neither parser nor parser-state has a custom Drop implementation. The rest of the state can be dropped normally. `ApplyPatchArgs` already has Debug and PartialEq, so existing `assert_eq!(finish(), Err(...))` has the required derives at source level.
- `finish().expect(...).environment_id.as_deref()` borrows a temporary only for the assertion statement. No escaping reference is introduced.
- `streaming_parser` and `ApplyPatchArgs` are private crate implementation details. Checked parser references are only in streaming_parser.rs, parser.rs and streaming_parser_tests.rs; the production path is parse_patch_text.

## Parse errors and completion

- Header validation, update-hunk validation and the entire process_line body were independently compared byte-for-byte and are unchanged.
- push_delta errors still propagate before finish. There is no new acceptance fallback, suppressed error, reordered filesystem write or changed line counter. Partial state on a push error was already possible; this patch does not make parsing transactional.
- finish still processes a buffered final line, handles the trimmed end marker, rejects empty update hunks, and requires EndedPatch before producing a result. New success transfers the same owned values instead of cloning them.
- parse_patch_text returns the same ParseError value on failure and drops the parser. apply_patch still rejects environment selection before filesystem canonicalization/verification/mutation.

## Concrete qualifications and non-blocking risks

1. **Private API capability change, including error recovery.** A caller can no longer retain an independent snapshot while continuing the same parser, or call finish, receive an incomplete-patch error, append more data and retry on that instance. No checked production/test caller relies on these capabilities. Document this explicitly if reporting semantic equivalence; it is equivalence of the checked one-shot production path, not of every former streaming API use.

2. **One test oracle moved.** In large_patch_split_by_character, the final hunk kind/order assertions previously inspected the last emitted preview; they now inspect the consumed final aggregate. Monotonic preview counts and other preview-content assertions remain, and current implementation returns the exact same state slice. Nevertheless, 11 names / 39 assertion macros alone do not prove identical regression coverage. A future bug returning the wrong final preview ordering but the correct finish result could be missed by this particular large test. Optional low-cost refinement: after the loop borrow `parser.push_delta("")` for the existing final preview assertions, then call finish to assert completion. Alternatively keep the patch and accurately state that this assertion moved to the final-result boundary. No extra suite is warranted.

3. **Memory claim needs precision.** Moving retains the parser's original buffers and spare capacity. Avoid promising universally lower retained memory or quantified allocation-byte/RSS improvement: former snapshots and moved buffers can have different capacities. Removing the two full-hunk clone sites is directly established; runtime and memory magnitude are unmeasured. The production parser is fed once, not character-by-character, so no quadratic production claim is justified.

4. **Uncompiled status remains material.** Source inspection supports the receiver lifetimes, temporary assertions and partial field moves, but does not replace the codex-patch library compile/test target and formatter. No new compiler error was identified by reading, and no compile PASS is claimed.

## Independently completed checks

- Recomputed all 19 baseline Git blob SHAs against SOURCES.json.
- Verified unchanged process_line and header/update validation bodies.
- Verified no custom Drop implementation for parser/state in the captured Rust source.
- Searched checked codex-patch source for parser construction, push_delta, finish and environment getter call sites.
- Recounted 11 retained test names, 38 assert_eq and 1 assert macro.
- Ran `git apply --check --whitespace=error` on the captured before tree successfully; this does not execute project code.

The existing source-only candidate is suitable to carry forward for compile/test qualification, with the above bounded API/coverage wording. No upstream changes or publication were made by this review.
