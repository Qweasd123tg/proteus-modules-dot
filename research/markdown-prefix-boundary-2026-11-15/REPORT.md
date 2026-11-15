# Markdown prefix boundary: known EXT-L2 follow-up

## Status

**Source-only, uncompiled proposal. Not a new finding or a verified runtime fix.**

This follows EXT-L2 in the published [PR85 extensions report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/9ac58bcd0bed9580016554a8cb48e42d4d3c3ed9/research/proteus-continuous-audit-2026-11-13/evidence/round2-extensions/REPORT.md). That report reproduced warm/cold divergence with both a production Document test and a real NDJSON renderer on older Extensions revision `4df3d0f7c168aa2947a5b014cf02f92984499d3f`. Those historical runs were not repeated here.

Fresh refs:
- Extensions main: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
- Delivery main: `9ac58bcd0bed9580016554a8cb48e42d4d3c3ed9`, including #153.

No upstream or live user source was modified. No renderer process, GUI, provider, external fixture, project script or Rust test was executed.

## Invariant and minimal change

A retained prefix can be reused only while the boundary condition that certified it still holds.

[Current code](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/f82b3ad753cf397f8a931b193aa1943af1ef07a7/packages/markdown-render/src/render.rs#L50-L58) hashes `source[..end]`, excluding the byte at `end`. [Prefix creation](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/f82b3ad753cf397f8a931b193aa1943af1ef07a7/packages/markdown-render/src/render.rs#L128-L143) additionally requires that excluded byte to be CR or LF: the closing fence's line must have ended.

Replacing that newline with text leaves the retained hash unchanged, although the former closing fence may no longer be a closing fence. The known example first renders a completed Mermaid fence followed by newline, then replaces that newline with text continuing the closing line. Warm rendering retains a completed child; a cold parse treats the same final input differently.

The candidate repeats the existing ended-line check before prefix reuse. It fixes the missing dependency rather than special-casing Mermaid or disabling streaming:
- One shared production path covers root code and display-math blocks, claimed or unclaimed, including literal Markdown fences.
- The parse boundary stays at the same byte offset. No delimiter is consumed or moved into the prefix.
- CR/LF remain a semantic class. A transition between LF and CRLF may retain the prefix because the suffix is reparsed from the old boundary.
- If only LF is replaced while CR remains, CR can still terminate the line. The candidate does not force a full parse for every CRLF edit.
- EOF or a non-newline at the old boundary invalidates the prefix. Even a valid added space/tab before newline conservatively causes reparsing.
- Language selection, fingerprints, source payload, ordinals, definitions, single-prose exact reuse and retained child ownership are unchanged.

No new helper framework, state, dependency or public contract is introduced.

## Cost and scope

Production change is **+6 lines**, including two explanatory comment lines. Another three lines register tests; the separate test module is 105 lines.

The reuse decision adds a constant-time byte lookup and comparison, with no new owned source copy or retained state. Losing the delimiter can cause a full parse of a large document, including when trailing whitespace leaves the closer valid. This is the conservative correctness cost of that edit, not a measured latency improvement.

Ordinary tail appends with the same ended-line boundary keep the existing incremental path. Existing prefix hashing still inspects the prefix; this patch does not make total rendering work proportional only to the tail. The `parsed_bytes` counter measures input to `fences::parse`, not all hashing or HTML conversion work.

This is not a proof of universal warm/cold equivalence. **EXT-L1 document-wide footnote definitions, numbering and backlinks remain unresolved.** Reference-table behavior and other document-global dependencies were not changed.

The earlier published pure-prose no-op patch is already reflected in this baseline; its fast path remains untouched. It was not reapplied or rebenchmarked. #153 concerns workflow private identities and is unrelated.

## Proposed checks: NOT COMPILED / NOT RUN

Four tests call the actual production Document for both warm and cold renders and inspect `parsed_bytes`:
1. Claimed Mermaid, unclaimed code and literal Markdown fence closing-line edits; LF/CRLF; inserted text, Unicode and whitespace.
2. Display math with two/three dollar markers and the same boundary edits.
3. Delete the line terminator to EOF, restore it, then append: revalidation followed by restored prefix reuse.
4. Preserved ended-line appends, LF/CRLF transitions, and replacement of LF with retained CR.

These are proposed Rust regressions, not executed results. No Python parser or string model was used as a replacement for renderer behavior. Existing tests are unchanged.

## Work actually verified

- Ten source blobs match pinned Git identities: seven current Extensions files and three published prior artifacts.
- Patch application and reverse application succeeded with zero fuzz in an owned copy.
- Both applied target files matched the candidate bytes; reverse restored all seven copied baseline files and removed the new test file.
- Added patch lines have no trailing whitespace.
- Independent design and exact source reviews accepted the bounded candidate without identifying a source blocker.

See `SOURCES.json`, `VERIFICATION.md` and `REVIEW.md`.

Rust, Cargo and rustfmt are unavailable. Python 3.12.14 and system patch were used only for text/hash checks. No compile, formatting, test, wire or GUI success is claimed.

## Remaining validation

Before claiming EXT-L2 is fixed:
- Run the documented `cargo test --locked -p extension-markdown-render` target with the project's pinned dependencies.
- Build the affected extension through the normal package workflow.
- Re-run the existing warm/cold NDJSON regression using the candidate binary and revision-changing source replacements.
- Verify the added line-ending matrix against actual markdown-rs behavior and retain the existing streaming/prose tests.
- Do not treat this as resolution of EXT-L1 or a full renderer audit.

Patch SHA-256: `3dfb094dd8129bc554cc8355b7930547dc140875faa041e50e69721a3b9d4222`.

