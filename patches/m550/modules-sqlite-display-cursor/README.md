# Modules: reuse one SQLite cursor during strict display open

`OpenDisplaySnapshot` used the ordinary per-record SQLite seek loop. For the
built-in writer's exact ordinary rowid table in a fresh, pinned read transaction,
use one ordered cursor instead. This only changes validation replay query shape.
The separate complete prefix SHA pre-scan, raw payload checks, canonical
identity/schema/sequence checks, semantic fold, optional saved-cut digest,
EOF digest comparison, state/staging caps and page cursors remain in force.

The optimization does not trigger for views, alternative table declarations
(even equivalent DDL formatting), statements whose schema introspection fails,
missing databases, non-pinned connections, or previously advanced cursors.
These retain the original per-record seek or backend scan. SQLite WAL
updates do not broaden the pinned transaction. JSONL retains its original
sequential scratch read. No change to SQL writes, durable representation,
contract definitions, network settings, or product lock files.

**Base** is complete historical Modules M368, 609 files, Git tree
`cbd95089580fedf54d668e7e5d2e13fea886f347`, archive SHA-256
`c60d90058dc93f99890c20788a07e19969703ea2a2cb14d39e0b239c164412dd`.
Verified all bytes and modes against an independent M362 + exact #608 replay.
The three-file production diff applies and reverses exactly. Independent forward
post-tree `496938d1d62f1f0c22e98da944f301b6ae70fcf8`.
Only `source.patch` is the product diff.

**Native checks.** Four distinct Rust 1.95.0 native test binaries with exact
pinned Core SDK `0c1b7572313230e5d123e95c722e1258a2e9ecd6` and verified vendor
dependencies, for before/after under default and preserve-order serde. 103
tests each: all 100 existing tests plus three new service-edge tests. The
original ignored test and separately executed large fixture are not counted
in 103. New controls exercise both nonstandard table and view fallback,
identity/gap/full-SHA rejection including still-pinned older handles, and a
deterministic WAL commit after record 1 is decoded. The open snapshot sees
old record 2, fresh opens see the new record, and comparison correctly rejects
a changed prefix. Existing tests exercise remembered-cut validation, page
retry/rewind, cross-request pending rows and source corruption.

**Large route.** The identical canonical 50,000-record no-model fixtures are
read through the actual service `OpenDisplaySnapshot → ReadDisplayRecords`
and exact response-contract validation. On SQLite, the validation replay goes
from 50,001 per-record seek executions (including EOF) to one ordered query,
under both layouts and on both sides of the 32 MiB state cap. SQLite
was already reusing the prepared seek statement; this counts executions,
not SQL compilation. The one schema-gate query and unchanged initial prefix
SHA query are not part of the replay count. JSONL is an unchanged control.
For the fitting fixture, all 200 staged pages, entire record-byte digest,
50k validated rows, state size, fixed prefix hash and fingerprint bytes match.
Above cap, full validation still completes, no display projection is exposed,
and the canonical fallback opens and returns its first page.

This is structural query-count evidence, **not** a wall-clock latency, RSS/PSS,
renderer, or end-to-end product claim. It does not avoid decoding records,
durable verification, writing the private stage, or later reading its pages.

**Reproduce.** Use pinned Rust 1.95.0 and an authenticated vendor directory:

    python3 proof.py --modules /path/to/Modules-M368-source.tar.gz \
      --core /path/to/pinned-Core.tar.gz --vendor /path/to/vendor \
      --work /path/to/new-work --target /path/to/new-target

The proof checks exact source archives, all locked registry checksums, all
three patch pre/postimages and strict inverse application. It then builds
independent crate tests, seeds one synthetic immutable corpus, and checks
functional results plus before/after statement counts and exact wire digests.
Use `--prepare-only` to verify inputs and exact patch without a native build.
The local receipt uses freshly compiled test executables linked directly to
the same authenticated build artifacts; the portable Cargo entry point clears
prior same-name package artifact outputs before compiling each arm.
