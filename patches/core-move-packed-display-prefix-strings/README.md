# Move packed prefix strings into the cache object

Exact base: [Proteus-core at b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14), `crates/proteus-core/src/core/session_store/remote/view/{cache.rs,prefix/packed.rs}`.

The display-prefix cache no longer copies its five already-encoded Base64 strings into a JSON object. The existing typed serializer still checks the actual JSON byte length against the same inclusive 64 MiB limit before an object is built. Object field order matches the derived serializer, and call IDs still go through real Serde in their existing array order. The value has the same compact JSON bytes and canonical hash input. The hash function, source snapshot, write key and conditional acknowledgement handling are unchanged. Generic display-page conversion and the prefix decoder are unchanged.

This affects the prefix write used by a cold full display-cache save as well as by incremental append. It does not remove the original Base64 encoding, the final output strings, or the subsequent transport. It does not measure whole-launch memory or startup speed.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

## Verification

The exact source inputs are listed under `reproduction_inputs` in `SOURCE-PROVENANCE.json`; save each under its key plus `.ref`. The proof dependencies are pinned to the actual Core lock. For reproduction, place the exact isolated lock text from the provenance at `DEPS/lockseed/Cargo.lock`. Put the listed official crates.io archives under `DEPS/archives/<name>-<version>.crate`, verify their SHA-256 first, and extract each matching top-level package directory into `DEPS/vendor`. The Cargo directory-source `.cargo-checksum.json` records the archive SHA as `package` and each original regular file's SHA under `files`, using paths relative to that package directory. Do not run a crate archive before verifying it. The proof checks archive and vendor hashes and runs Cargo offline and locked.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc --cargo /path/to/pinned/cargo --deps /path/to/DEPS
```

Rust 1.95 passed 6/6 tests in each of four lanes: debug and optimized, with default `serde_json` map behavior and with `preserve_order`. The isolated test uses actual locked Serde, serde_json 1.0.151 and Base64 0.22.1. It compares the same immutable call set across both variants and exercises real encoded bytes and decode, malformed inputs, the exact byte limit and +1, and the exact prefix write logic with inert storage/acknowledgement and digest callbacks. The production canonical serializer was tested byte-for-byte before digesting; Ring, a real worker, and the full Core application were not run. Exact two-file apply/reverse and rustfmt passed.

On the 50,000-row synthetic certificate, the five string payload pointers are preserved. Scoped conversion removes five allocations and 4,902,240 requested bytes in each lane, with no reallocations. This excludes preparation, hashing, cache transport, and persistence, and is not a process RAM, peak, or latency measurement.
