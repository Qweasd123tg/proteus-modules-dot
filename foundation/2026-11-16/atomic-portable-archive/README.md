# Atomic replacement of portable archives

Source: [Desktop 79499f2](https://github.com/Proteus-harness/Proteus-desktop/commit/79499f2d639a3185384bed75f29b6919b811fe7c), `scripts/portable.py` and its existing serialization tests. Proposal only: upstream has not been modified.

## Confirmed failure and bounded repair

`archive()` opens the deterministic final tar.gz in truncating mode before adding package files. An exception can therefore destroy a previous successful archive. An inert-file reproduction with an injected `TarFile.add` failure changed the old archive from 1326 bytes to an incomplete 53-byte file. No compilation, installer or downloaded code was run.

The patch creates the tar.gz inside a private temporary directory under the same build directory, closes compression successfully, and only then uses `os.replace` to publish. The temporary directory is cleaned on pre-publication failures. Existing archive permission bits are preserved; a new archive uses ordinary creation permissions under the current umask. No global umask mutation or extra dependency is introduced.

Two regression methods are added to the existing serialization suite rather than creating another test framework. Add/compression/close/replacement failures preserve old bytes; successful replacement is readable and preserves the existing mode. New-file creation permissions are checked against an ordinary file created in the same environment.

## Verification

- Author: existing 18 Python tests passed; the final candidate's 20 tests passed. This earlier complete run included the existing tiny Python flock subprocess test. It did not run project executables or native builds.
- Later restricted author run: only the two new file-only methods; candidate passes, baseline violates archive preservation.
- Independent reviewer: reran those two methods in a fresh copy; added first-creation failure checks for add and replace, confirming neither a final archive nor temporary residue remains.
- Strict patch apply, exact candidate bytes, reverse and exact original bytes confirmed independently. Both target files were checked against the exact upstream ref.

These are actual Python/file-operation checks, not Rust/runtime acceptance. Native Desktop, real component builds, hosted CI and benchmarks were not run. No speed or memory gain is claimed.

## Contract limits

This protects a prior archive from ordinary exceptions before archive publication. It does not make package-directory publication and archive replacement one transaction: the portable directory may already be updated when archive generation fails. It does not add fsync/power-loss durability, source-snapshot isolation against outside writers, archive authenticity, symlink policy or provenance-hash enforcement. Existing final symlink/hardlink identity is not preserved by atomic replacement; the archive path names the new regular artifact.

Separate staging-symlink and hash-policy observations are intentionally excluded from this patch. The process/cancellation investigation is not part of this proposal.
