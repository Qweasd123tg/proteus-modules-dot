# Core: format selection digests into one buffer

Session model-selection bindings and filenames keep the same SHA-256 digest and lowercase 64-character text. The encoder now reserves the final string once and appends the two ASCII hex digits for each byte. It no longer creates a separate formatted string for each byte.

This changes only formatting after the digest call. The serialized input, hash algorithm, resolved profile paths, binding comparisons, filenames, and persistence rules are unchanged.

## Exact offline check

Use the unpatched file from `Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`, installed Linux x86-64 Rust 1.95.0, and an existing private scratch directory:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock /path/to/Proteus-core/crates/proteus-core/src/app_server/session_selection.rs \
  --rustc /absolute/path/to/rustc \
  --work-dir /path/to/private-scratch
```

The proof checks both source identities and patch replay in both directions. It lifts the exact stock formatting after the digest and the exact candidate encoder. Five tests passed in each of debug and optimized builds, covering all 256 input bytes, all 65,536 ordered pairs, 12,000 generated 32-byte inputs, and known or leading-zero digest values. The scoped formatter counter observed 35 allocation or reallocation operations before and one after on a fixed input in each build. The test does not run ring hashing, real persistence, or full Core, and does not measure startup time or process memory.
