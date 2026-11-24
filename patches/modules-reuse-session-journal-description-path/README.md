# Modules: keep the journal path already used to open a session

`sessions::open` builds the selected backend's canonical record path, borrows it for the journal metadata and WAL recency checks, then builds the same path again to return the session descriptor. Move the existing `PathBuf` into `record_location` instead. The backend path functions only join a fixed filename to the same resolved directory; the second construction and temporary backend box are unnecessary.

Only `source.patch` changes production source: one line in `storage/session-storage/src/service/sessions.rs` at [Modules 331cfc20](https://github.com/Proteus-harness/Proteus-modules/tree/331cfc20bbaf821ab07de49868426da29ebdeb64). No fallback, file probe, identity/retirement check, WAL policy, sort rule, journal reader, public type or format changes. `Create` and `Describe` still construct synthetic descriptors as before when a session has not been materialized. This patch is independent of [#582](https://github.com/Qweasd123tg/proteus-modules-dot/pull/582); the verifier checks the exact bytes of all four source subsets, both apply orders and both reverse orders. No runtime claim is made for the composition.

## Native evidence

The proof builds the full `session-storage` crate twice with its two original Core subcrates at their pinned source commit. Its fixtures take the same API entry point as the native caller: `StorageService::execute`, rather than a mock or extracted function. It validates typed results, compares exact serialized traces of the typed responses and saved catalog indexes over the same physical files, and requires preservation of raw journal and identity bytes within each arm.

- The directory and journal filename produce identical `Open` descriptors. Existing `Create`, `Describe` and both global and workspace-scoped `ListCandidates` return exactly the expected descriptors; a tied-recency list preserves descending locator order. The metadata routes decode and fingerprint zero journal rows.
- The actual cold `List` writes the same bytes. Candidate also reads the stock-generated sidecar exactly as left by stock, with no decodes or journal hashing and with unchanged sidecar bytes, before its own cold replay. Audits still decode the source independently without changing a published sidecar.
- Real JSONL torn tails are excluded from the committed extent and checksum without repair. A complete corrupt tail is skipped by ordinary `List` and rejected by audit. A materialized JSONL session with no journal still uses directory mtime and returns the selected description path. Wrong-format rejection, absent paths, and SQLite/JSONL empty versus nonempty WAL recency policies are preserved.

## Allocation observations

One of two independently seeded default-map release pairs:

| Native request | Rust heap peak, stock → new | Requested bytes, stock → new | Allocation calls including realloc, stock → new |
|---|---:|---:|---:|
| Open directory, JSONL | 1,356 → 1,356 | 4,934 → 4,604 | 61 → 58 |
| Open directory, SQLite | 1,356 → 1,356 | 5,025 → 4,607 | 61 → 58 |
| ListCandidates, 24 JSONL sessions | 26,714 → 26,714 | 158,082 → 150,162 | 1,700 → 1,628 |
| ListCandidates, 24 SQLite sessions | 26,714 → 26,714 | 160,280 → 150,248 | 1,701 → 1,629 |

The measured result is less allocation traffic, not lower peak or retained memory. The zero-candidate and missing-path controls are exactly unchanged. The full native executable includes 97 upstream tests passed, 1 upstream test ignored, and a separate paired proof test that actually exercises the new cases only during the explicit paired invocation. See `verification.json` for both release repeats, map-layout/profile coverage, exact byte digests, source pins and allocator counters.

These are Rust allocator observations around metadata-only native requests on Linux x86-64, not Desktop startup, latency, RSS/PSS, process RAM, or SQLite's C heap. Inputs are prepared outside the measured phase; owned requests are cloned inside scope before the phase, and the meter carries that exact live balance forward. Returned responses are live at the phase endpoint and are then dropped with the service; the meter requires zero counted bytes left. Requested bytes include the entire new size of each realloc. Cold list parity is not a cold-list allocation or timing benchmark.

## Replay

Requires Python 3.11+, Git, a C toolchain for bundled SQLite/Ring, Rust/Cargo/rustfmt 1.95.0 Linux x86-64, the pinned Modules and Core checkouts, and the official registry archives described by the native lock. All 184 source files and both original locks are validated; the offline replay resolves the exact 157 registry archives.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --modules /checkout/Proteus-modules \
  --core /checkout/Proteus-core-0c1b7572 --work /fresh/private/work \
  --toolchain-bin /path/to/rust-1.95.0/bin --archives /path/to/official-archives
```

Repeat `--archives` for multiple directories. The test overlay is identical in both arms and is not a product change. Each arm's native leaf is explicitly rebuilt and its artifact checked against the intended source path; work with frozen executables when pairing runs. No network is used during build or replay.
