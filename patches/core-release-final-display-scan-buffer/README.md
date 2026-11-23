# Release oversized staged transcript scratch before the final callback

Exact base: [Proteus-core at b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14), `crates/proteus-core/src/core/session_store/remote/snapshot/display_records.rs`.

Decode each record into its owned value just as before. If its callback is the expected last one and the raw scratch capacity exceeds 4 MiB, release the scratch before handing off the decoded record. The count is only an allocation-lifetime hint: the reader still reads through EOF, invokes all valid record callbacks, and validates the actual count afterward. The staging byte limit, LF and parse checks, reader and callback error order, replay fallback, and non-staged path are unchanged.

Ordinary lines reuse the existing scratch. A small expected-final record can also release large capacity retained from an earlier record, but an earlier large record's own callback still sees the scratch live. The raw buffer remains necessary during deserialization. Releasing it does not imply that the allocator returns memory to the OS.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

## Verification

Use the exact source files listed in `SOURCE-PROVENANCE.json` under their key plus `.ref`. Put the embedded proof lock text at `DEPS/lockseed-min/Cargo.lock`. The listed official archives were checked against Core's lock. Use the R257 verified base archives for the shared crates and `DEPS/archives` for UUID; extract the checked packages into `DEPS/vendor`. Each Cargo directory-source `.cargo-checksum.json` uses the archive hash as `package` and each relative regular-file hash in `files`. Cargo runs offline and locked.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc --cargo /path/to/pinned/cargo --deps /path/to/DEPS \
  --base-archives /path/to/verified/base/archives
```

Rust 1.95 passed 6/6 in both debug and optimized modes with real serde_json 1.0.151 and UUID 1.23.1. The isolated fixture compiles the exact staged scan with the production journal envelope and HistoryMutated/text shape, narrowed to the record and part variants it tests. The proof uses physical files for normal reads and a controlled reader for rewind and late I/O faults. It checks extra, missing, malformed and incomplete records, callback error priority, the exact capacity boundary, two consecutive giant rows, and a small final row after a giant. Raw allocation lifetime is witnessed by the actual allocator deallocation, not inferred from a smaller length. The source patch applies and reverses exactly and passes rustfmt.

With 50,000 synthetic text rows in one typed history mutation, the staged LF record is 32,689,290 bytes. Its 33,554,432-byte raw allocation is live at callback entry in stock and released beforehand in the candidate, on both rewind scans. Scoped request counts on the small and consecutive-large controls were identical. No real worker, renderer, full application, owner data, process RAM/peak or latency was measured.
