# Build the SQLite memory MATCH operand without per-token strings

Exact base: [Proteus-modules at 331cfc20](https://github.com/Proteus-harness/Proteus-modules/tree/331cfc20bbaf821ab07de49868426da29ebdeb64), `context_provider/sqlite-memory/src/lib.rs`.

Build the MATCH operand in one output `String` by appending borrowed spans. Keep the existing whitespace split and Unicode scalar eligibility predicate. Every eligible token gets the same quoted prefix operand, in the same order; replace NUL with one space and double internal quotes as before. Two ASCII special characters delimit the spans on valid UTF-8 boundaries. If no token is eligible, the result is still empty, keeping the current recent-items branch. SQL, bound parameters, locks, ranking, and storage are unchanged.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

[#305](https://github.com/Qweasd123tg/proteus-modules-dot/pull/305) is already included in this base. Its pinned artifact changes the cached INSERT and its regression test, not the read operand. Do not reapply it.

## Verification

Use the pinned inputs from `SOURCE-PROVENANCE.json`, under the indicated `*.ref` names.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc
```

The exact old and new pure operand builders and their existing direct unit test passed 8/8 in both Rust 1.95 debug and optimized modes. Coverage includes 65,536 small combinations, 4,096 longer generated inputs, all valid Unicode scalars in a single combined fixture, return-empty controls, and exact NUL and quote cases. The proof also checks that every byte outside the helper is unchanged. The raw patch and reversal passed in private scratch; rustfmt passed. No database, SQLite engine, real queries or full crate were run.

For the direct `React Router!!! v6` fixture, allocations plus reallocations fell from 13 to 4, and summed requested bytes from 205 to 120 in both modes. The output length is unchanged, but geometric growth can leave more final spare capacity: 35 bytes to 64 in this fixture. The short and escaped fixtures also requested fewer total bytes; the empty fixture still made no requests. These are scoped allocation counts, not peak memory, RSS/PSS, latency, or SQLite performance.
