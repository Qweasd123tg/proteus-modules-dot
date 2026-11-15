# Text-boundary proposal composition

Status: source-text compatibility check of already published #115, #116, #119 and the #124-on-119 variant. No new production edits, new findings, behavioral model or tests were introduced. No project code, runtime, real file-tool operation, command session or provider was executed. No upstream repository or live data was changed.

Scope was deliberately restricted to the published changed hunks and their text application. #115 was considered only as its existing UTF-8 byte-collector proposal, not as a review of adjacent execution, reader/session lifecycle, cancellation, PTY or security mechanisms. Those excluded directions were not reopened. Whole files copied for byte identity are not a claim of reviewing their neighboring functions.

## Exact inputs and dependency

Fresh Modules main: `c035142558f0fca43e9772fc0e50ca293abf1531`.
Delivery input commit: `54d16ecaa2fdcc5fb4758b82fdb708dd9156b0a2`.
The copied Modules Cargo.toml retains actual Core pin `41bdfffa6e70228278b4abc758b7f81a12672f35`; it is not changed or qualified by this pass. No Core patch, dependency, public DTO or protocol change is included.

This follows [PR155's bounded integration plan](https://github.com/Qweasd123tg/proteus-modules-dot/blob/54d16ecaa2fdcc5fb4758b82fdb708dd9156b0a2/docs/integration-plan-2026-11-15.md), not a new defect report. Earlier proposals already recorded relevant pair/group composition; this pass compares the complete selected four-patch text result.

| Selected input | Published path under `foundation/2026-11-15/` | Git blob |
|---|---|---|
| #115 | `utf8-poll-boundary/utf8-poll-boundary.patch` | `3d7f8c7d2dbd43c83d7468067e3befa99e6d623e` |
| #116 | `direct-patch-eol/direct-patch-eol.patch` | `976cb3343e91aab3f7c7420865236516f81d0628` |
| #119 | `file-read-utf8-invariant/bounded-read-utf8.patch` | `07db80b59bc6996b396e2a5edd52bb85d449294c` |
| #124-on-119 | `range-eol-invariant/range-eol-on-PR119.patch` | `1a78b8a61ff6d171c266641f24f75d8f0292acd2` |

**Required order:** #119 before the selected #124 rebase. #115 and #116 are independent of that dependency. The standalone `range-eol.patch` (blob `7292696723678dfea8cb114527928e823148c162`) is an excluded alternative, not an additional patch. Its previously documented context conflict with #119 is not claimed to have disappeared. This pass used the published rebase verbatim, without new conflict resolution.

`composed-text.patch` is a mechanical **alternative** representing the selected originals on unmodified Modules c035. It is not an extra layer to apply after them. A partially patched tree requires its own checked remaining delta; do not force this combined patch or then reapply its originals. No implementation was added beyond the exact selected inputs.

## Preserve different contracts, not one universal decoder

The useful integration constraint is that these proposals must not erase one another's deliberate representation boundaries:

- **#115, lossy streamed output:** retain only an incomplete trailing UTF-8 scalar between nonterminal collections, at most three bytes. Definite invalid/binary bytes retain the lossy presentation policy. Final collection flushes the remainder through that same policy. Terminal status is not proof of complete EOF, and head/tail truncation is not repaired here. This is not the strict file-reading decoder from #119.
- **#119, strict file text:** ranged and batch raw reads share borrowed `decode_read_bytes`. Incomplete suffix is permitted only at an established byte-budget boundary, not merely because old metadata suggested a larger file. Observed EOF requires valid UTF-8; invalid interior bytes remain errors. Already rendered valid String truncation stays a separate char-boundary operation. Full read remains unchanged.
- **#124, semantic versus display range:** unnumbered ranges preserve actual separators between selected lines, including mixed LF/CRLF. The last selected line terminator is still omitted, and numbered output remains LF display text. The rebased hunk retains #119's exact decoder call and `end < line.len() || !complete` eligibility. Separator byte length is charged to the output budget, so preserved CRLF can leave less capacity than normalized LF.
- **#116, direct-patch EOL:** split/check/render choose CRLF only when the source has CRLF and every LF is part of CRLF. Otherwise the original LF path remains, including mixed-EOL limitations. Add File remains LF; no-newline and bare-CR semantics are not replaced by range-reader policy.

Thus #124 preserving mixed separators does not imply #116 supports arbitrary mixed-EOL hunk matching. Nor does #115's lossy final output permit a file reader to silently drop malformed EOF bytes. There is no new shared framework joining these different policies.

The source comparison retains both additions to `docs/reference.md`, the file-tool description of numbered versus plain ranges, the shared file decoder and all proposed test registrations. The range rebase does not replace or duplicate the decoder introduced by #119.

## Limits and costs remain

These are not universal byte-roundtrip or edit-success guarantees. Range output omits its final terminator; numbered/batch-display text is not a raw edit preimage. Exact edits still depend on a suitable unchanged, unambiguous snippet. No stronger snapshot or multi-editor consistency is introduced.

Only an already recognized inter-line delimiter is preserved atomically. Raw scan cuts can still occur before an unseen LF. Existing conservative line-limit/EOF metadata and zero-capacity admission remain. Budget-success prefixes do not validate unread file suffixes.

Direct-patch mixed-EOL matching remains limited; no new insertion convention or whole-file normalization is selected. #115's original truncation and final-collection limits remain. No process-lifecycle correctness claim follows from this text composition.

Static changes have tradeoffs: #115 can delay up to three bytes, #116 adds a source scan, and #124 can fit fewer bytes/lines under the same limit because CRLF costs two bytes. #119 removes duplicated raw decode policy and redundant rendered-string decoding. None is a measured CPU, memory, latency or throughput result. The full combined diff is +651/−61 lines across 14 files, mostly retained tests. Composition itself supplies no further optimization or implementation change.

## Mechanical evidence

`SOURCES.json` records 19 verified blobs: 13 Modules baseline/source-metadata files plus six published inputs/documents (four selected patches, the excluded standalone #124 and the plan). The Modules tree was fetched again; cached baseline bytes were rehashed against that exact tree before copying. Published patch/doc bytes were fetched again and Git-blob verified. Baseline copies contain only selected target files and repository metadata, not a complete buildable checkout.

System `patch --batch --fuzz=0 -p1` dry-run and application succeeded for exactly these orders:

1. #115 → #116 → #119 → #124-on-119.
2. #119 → #124-on-119 → #116 → #115.
3. #116 → #119 → #115 → #124-on-119.

All 14 target files are byte-identical. No conflict, manual edit, force or fuzz was needed; the tool accepted line offsets. Other legal permutations and the standalone #124 combination were not applied in this pass. Equality concerns target files, not patch-generated `.orig` backups.

The combined diff also dry-runs/applies to another owned baseline copy and matches the 14 target hashes. Reverse application restores all 13 baseline files and removes seven new target files. `COMPOSITION.json`, `COMPOSED-TARGETS.json`, dependency metadata and logs record this text evidence. System `patch` is not the project's direct-patch algorithm; that project implementation was not executed or modeled in Python.

Python was used only for file/hash/diff/source bookkeeping. No Python substitute implementation or behavioral test was run. `SOURCE-CHECKS.json` contains literal checks of the changed representations/registrations, not semantic execution assertions.

## Qualification status

The combined source retains 25 proposal-added Rust test functions: #115 six, #116 seven, #119 seven and #124 five. None is a new test from this pass; none was compiled or run. The proposed tool-level tests in the originals do not become actual tool execution because their source is present in this bundle.

`rustc`, `cargo` and `rustfmt` are unavailable in the selected PATH. **NOT COMPILED / NOT RUN:** formatter, Rust tests, project scripts, fixtures and application/runtime integration. Historical reproduction results are not transferred to this tree, and text applicability is not a compile, behavior or CI PASS. No dependencies were installed.

Independent exact source-text review is recorded in `REVIEW.md`. The result is a handoff of text compatibility and an alternative patch, not a production recommendation. Any later qualification would need its separately authorized actual toolchain/tests; no excluded investigation or runtime step is implied by this handoff.

Combined patch SHA256: `ca795a23a90abefd4ef7475621ce2becadf7242e46d7fd96dbe8921a072e612c`.
