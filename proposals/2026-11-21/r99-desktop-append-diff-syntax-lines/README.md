# Append Desktop diff lines directly to the syntax source

One-file proposal for Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`, also verified on sealed M150 through Desktop #421.

Preparing a file for syntax highlighting builds one source string for the old side and one for the new side. The old code allocated a temporary replacement string for every nonempty included row and copied it into the source, even when the row had no tabs. Context rows did this twice. The new code appends borrowed pieces directly, with exactly four ASCII spaces for each tab. Both aggregate strings are still built. Nothing changes in the parser, synthetic newlines, byte ranges, selected language, cache invalidation, row display, width measurement, highlights mapping, clipboard, or view behavior. This is highlight preparation work, not the cost of ordinary cached frames.

## Focused verification

- All **50 predecessor patch hashes** through #421, the sealed M150 source, and seven locked dependency identities checked. The candidate builds from one clean change to `src/ui/diff/syntax.rs` in both source tiers. Eight fresh Cargo-selected executables bound to their exact inputs and pre/post binary hashes: four local diff parser test binaries and four headless probes. **13/13** stock and **15/15** cumulative parser tests passed in each baseline and candidate arm.
- All four probe traces agree byte-for-byte (SHA-256 `08f1d43fb1853be38815d834d605b551bed656b24177deda06cd8a4ad78552a1`). The probe executes the exact production syntax-source loop and span projection, captures the source at the highlighter input, and compares those bytes and every row interval to the original replacement rule. Fixtures include CRLF, tabs adjacent to UTF-8, consecutive and trailing tabs, blank/context/added/removed/hunk/note rows, no-final-newline markers, a rename across languages, multi-hunk and metadata-only files. Synthetic cross-row styles test the exact row-relative byte mapping.
- Allocation/reallocation requests while assembling **both** sides of each synthetic 481-row file (360 eligible nonempty rows per side):

| Fixture | Requests, before → after | Requested bytes, before → after |
| --- | ---: | ---: |
| Space-indented | 744 → 24 | 114,286 → 88,576 |
| Sparse Unicode tabs | 1,464 → 26 | 199,012 → 154,112 |
| Dense tabs | 2,184 → 30 | 401,488 → 285,216 |

The assembly count includes growth of the destination strings and the ranges vector but excludes file construction, the highlighter and span mapping. As a separate control, appending a nonempty tab-free or tabbed line to an already-capacious destination made zero allocation requests in the candidate; a blank append was already zero. Requested bytes are summed allocation sizes, not peak or retained memory. The probe models Rope input and highlight effects. No live Desktop window, real tree-sitter styling, process memory, latency, or full app build is claimed.

## Reproduce

Run `sha256sum -c SHA256SUMS`, then `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` for static composition, apply/reverse and formatting. Use `--run` only with the existing warm `CARGO_HOME`, `CARGO_TARGET_DIR`, common `R99_BUILD_LOCK`, and a fresh private `R99_RAW_CARGO_DIR`. It builds locked offline, one job, using the common minimum free-space and growth fences. `python3 summarize.py RAW_CARGO_DIR EXISTING_RESULT_DIR` checks Cargo-selected artifacts, exact trace agreement, allocations, and local parser identities without rerunning the executables.
