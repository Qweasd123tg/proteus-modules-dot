# Files listing knowledge: unknown is not absent

Bounded source-only proposal for known [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) files-recovery #2.

Production changes +4/-6 lines across visit, prune, exists and cache invalidation converge on the existing Option invariant: failed listing is not evidence of deletion. No new dependency or state framework. Six proposed tests accompany the patch.

**NOT COMPILED; six new and five existing tests NOT RUN.** This delivery merges proposal artifacts only, not an upstream production fix.

Read REPORT.md for precise costs and limits, INDEPENDENT-REVIEW.md for source review, SOURCE-HASHES.json and REFS.json for pinned source identities. Source snapshots are intentionally not duplicated.

Child rows can still disappear during errors; no last-good/error UI is added. Retained expansion can increase retries. LOOKAHEAD bounds only collapsed lookahead, not expanded reads. Folded Expand All #1 and cached-root-None remain open.

## Apply and validate upstream

Use a clean Proteus-harness/Proteus-desktop-extensions checkout at f82b3ad753cf397f8a931b193aa1943af1ef07a7. Review the patch; git apply --check --whitespace=error-all files-listing-knowledge.patch then git apply files-listing-knowledge.patch. Before production acceptance, run cargo test --locked -p extension-files and appropriate native/wire checks. These commands are instructions, not evidence they ran.

## Publication verification

Publisher independently recomputed package/source hashes (8 exact Git blobs), checked strict git application, applied with fuzz=0, and compared both resulting source files byte-for-byte to the reviewed candidate. No project code was executed. No compiler, runtime or CI success is claimed.
