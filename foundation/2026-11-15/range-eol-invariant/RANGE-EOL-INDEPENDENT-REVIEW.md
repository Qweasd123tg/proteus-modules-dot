# Independent exact source review: range EOL invariant

## Verdict

No source-level blocker found in the exact candidate. This is a meaningful narrow correction of the known non-numbered range projection, not a new finding, not full-file byte-round-trip assurance, and not compile/test verification. No Rust, project scripts, tests, compiler, or application runtime were executed.

Baseline Modules c035142558f0fca43e9772fc0e50ca293abf1531. Coordinator reports 12 exact source blobs verified; own checks below cover candidate bytes. No production integration or publication performed.

## Implementation and boundaries

read.rs identifies the actual current EOL before removing it, then carries that delimiter forward only after accepting a selected line. The first separator remains empty. Skipped lines cannot insert a leading separator. Thus CRLF, LF, mixed separators, empty selected lines, and unterminated final lines preserve the source's inter-line bytes. A bare CR remains body content; CRCRLF removes only the last CRLF. No global normalization or new tokenizer is introduced.

The pending delimiter is not emitted after the final selected line. This deliberately preserves the existing final-terminator omission, including line-limit and EOF paths. A non-numbered output is a contiguous substring of the source for the accepted valid range, not necessarily all bytes of the selected full lines. Empty output is not a usable edit preimage. Numbered output keeps its old synthetic LF display; no raw-source guarantee applies there.

Budget arithmetic charges separator.len(), including both CRLF bytes, before appending. Saturating subtraction and available==0 preserve the existing refusal when no body capacity remains, even for an empty next line. A retained inter-line separator is never emitted partially. This does not make raw CRLF atomic at a scan boundary: a preexisting incomplete read can end in CR before an unread LF, without having observed a complete EOL. This can return fewer body bytes/lines than the previously normalized CRLF view, correctly accounting for retained source bytes. UTF-8 decoding, complete eligibility, per-line scanning, and metadata logic are otherwise unchanged. As before, UTF-8 prefix truncation may accept an empty text prefix of a last attempted line; returned_lines is not a guarantee of nonempty or complete line content.

The old decoder block is unchanged by this patch. PR119 composition must be checked separately; this review does not imply that all existing UTF-8 edge behavior is corrected here. PR116 edits another representation boundary and does not supply this behavior automatically.

## Literal edit and transport evidence

Inspected only relevant edit.rs matching/projection portions: nonempty old_string, exact content.matches, uniqueness unless replace_all, and literal replace/replacen. Therefore a unique nonempty returned range can serve as the old_string preimage for the demonstrated cases. Replacement EOLs remain the caller's literal choice; this patch does not force replacement newline policy, unique matching, or preservation of a changing file.

Actual-pin tool_support.rs ok_result embeds output directly as a JSON string. Escaping is wire representation, not newline normalization. Full read and read_many are not changed by this candidate. This does not promise downstream model rendering or hook preservation.

## Proposed tests, NOT RUN

Four internal tests plus one ToolModule-level test are plausible against source:
- LF/CRLF/mixed inter-line projection, skipped prefix, blank lines, bare CR, CRCRLF, empty/out-of-range cases, final selected EOL omission.
- Numbered LF display and conservative line-limit metadata.
- CRLF consumes two budget bytes; exact UTF-8 body fit and one/two remaining-byte cases reject the next line without a partial delimiter.
- Raw scanned-byte counts and observed-EOF metadata.
- Full/batch read controls plus literal range→edit cases for LF, CRLF, and mixed content, with normalized old_string negative controls.

Path attributes resolve read_eol_tests.rs as a child of read; super::* accesses private helpers/ReadOptions. tests.rs mod read_eol resolves src/tests/read_eol.rs; the existing invoke helper and imported tools are visible to the child. Borrowing old from ranged remains valid through the edit call. The internal type inference and serde Value assertions appear consistent. No compile or execution proof is claimed. Existing budget tests remain necessary; no performance or live end-to-end claim.

## Independently computed SHA256

- range-eol.patch: 0ce98894a787547953f819cb43b5e12a6834bdd66f7e7c1ee0e008e33eecf27d
- after/tool/file-tools/src/read.rs: 68170378932e9c90cef54dcf9dc036e68340f4aeab89ac79a3029161179feaea
- after/tool/file-tools/src/read_eol_tests.rs: c88b099772dd19d0cec4f7251cc25f72c17d43044786e39800d5d8d597ed3eeb
- after/tool/file-tools/src/tests/read_eol.rs: 4c48a107101134be1b5a9f59c56f0fe260783494835b5aa6694263cb6ba2d58d
- after/tool/file-tools/src/tests.rs: ffae0db66ec39f92f2aa54b02856f715bd0e42ae890f23e839d2f89234b33358

Exact composition/apply results are not asserted here pending separate evidence. Scope remains output EOL representation and literal matching; unrelated authority/concurrent-edit mechanisms were not audited.

## Explicit PR119 rebase and text composition addendum

Read range-eol-on-PR119.patch and compared final read.rs with the standalone candidate. Own patch SHA256 c9afa29286e6a149f2f0439eed207d6b2b2f579ba1c926e1703a39b1e5000fc8 matches. The only final read.rs differences from standalone are PR119's decode_read_bytes import and decoder block, retaining the same end<line.len() || !complete eligibility and post-decode end=text.len(). The EOL state/budget/output effect is unchanged. lib.rs declares read_text; tests.rs retains both mod read_eol and mod read_utf8. Both new EOL test files are independently byte-identical between standalone and rebased trees. No source blocker found in this resolution.

COMPOSITION.json explicitly records original patches failing in read.rs/tests.rs in both orders; do not describe them as automatically compatible. It records successful inert apply/check for three orders with PR119 before the explicit rebase and PR116 in different positions. Own diff -qr checks found combined-order-1, combined-order-2 and combined-order-3 byte-identical. This is text composition only, not compiler, test, runtime or behavior proof. No original or rebased production code was executed.

The delimiter wording above is narrowed to retained inter-line separators. Existing incomplete raw reads may terminate at CR before an unread LF; this candidate does not introduce whole-file raw CRLF atomicity or a new scan-boundary policy.

## Final report review

Read final REPORT.md in full and independently checked SHA256 06516d046efadc796b188b65559a09bc5219e33d577bab7d9514602350681b0d. No blocking overclaim found: it restricts preservation to inter-line separators, keeps final-ending omission and numbered display explicit, does not promise raw scan-boundary CRLF atomicity or arbitrary edit success, and discloses original patch conflicts and explicit PR119 rebase. Five tests and the suggested future gate are clearly not executed. Composition is accurately labeled textual, not runtime integration. The source-only acceptance verdict remains unchanged; no additional source changes or runtime execution occurred during this final read.
