# Core: borrow already-lowercase ASCII workspace search paths

The workspace file search scorer no longer constructs a lowercase copy when a candidate path is ASCII and contains no uppercase ASCII byte. Other paths still go through the same whole-string Unicode lowercase conversion, including contextual and multiscalar case mappings. The scoring rules, raw path tie-breakers, query normalization, candidate discovery, Git and walk scope, metadata checks, and caps are unchanged.

The base is `Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`. Delivery #260's query-term normalization is already present here. This patch changes path scoring only; do not reapply #260.

## Exact offline check

Use the unpatched file from the pinned Core commit, installed Linux x86-64 Rust 1.95.0 and an existing private scratch directory:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock /path/to/Proteus-core/crates/proteus-core/src/app_server/http/workspace/search.rs \
  --rustc /absolute/path/to/rustc \
  --work-dir /path/to/private-scratch
```

The proof checks exact forward and reverse patch replay and compiles both scorers, their query and subsequence functions, the unchanged ranking block, and the three existing unit tests from each arm. Eleven tests passed in each of debug and optimized builds, including 1,081,344 generated score pairs per build, explicit Unicode and stable tie-order cases, and 50,000 prebuilt lowercase paths with both hits and misses. The allocator recorded 50,000 operations before and zero after for the scorer on that fixture alone.

The fallback performs a byte-prefix check before Unicode lowering. This packet measures neither speed nor application memory, and does not run Git, filesystem candidate discovery, HTTP or the full Core package.
