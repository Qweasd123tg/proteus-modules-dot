# Move selected user history into local compaction output

Exact base: [Proteus-modules at 331cfc20](https://github.com/Proteus-harness/Proteus-modules/tree/331cfc20bbaf821ab07de49868426da29ebdeb64), `hook/codex-context-preparation/src/{compaction,history}.rs`. The locked Core SDK is `0c1b7572313230e5d123e95c722e1258a2e9ecd6`.

After the local summary succeeds, save the retained-user count and move the already owned vector into the replacement helper. The helper still inserts cloned ephemeral context before the last retained user, or before the summary if none remain. The fresh summary stays last. User payloads and identities, replacement mappings, estimates, diagnostics and error propagation are unchanged. This removes one deep copy of the selected user rows, not all history copies. The outer vector can still grow during assembly. Remote compaction is not modified.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

The unmodified [#517](https://github.com/Qweasd123tg/proteus-modules-dot/pull/517) and [#521](https://github.com/Qweasd123tg/proteus-modules-dot/pull/521) patch artifacts compose with this one. All six application orders and their exact reverse steps agreed byte-for-byte in private scratch. Neither prior is required to apply this patch on the declared stock source.

## Verification

Use the pinned inputs listed in `SOURCE-PROVENANCE.json`, named by each reproduction key plus `.ref`.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc
```

The exact local success/error tail, history functions, estimates and SDK constructors passed 17/17 in both Rust 1.95 modes, with 4,096 cases across stock, candidate and both variants carrying #517/#521. The proof covers zero, one and multiple retained users, image and truncated identities, diagnostic and context ordering, and unchanged propagation of mock summary error/cancellation. The full provider/retry implementation, native Cargo integration, and JSON serialization were not run. The complete source files were checked and reversed; the two changed files passed rustfmt as standalone and composed.

In a fixture under the real 20,000-token budget, the existing 72 KiB selected text allocation reaches the output without copying. Measuring the assembly helper after selection, allocation/reallocation requests were 7+1 versus 4+0 and summed requested bytes were 74,866 versus 338 in each source tier and build mode. Those scoped fixture counts do not represent process memory, peak, PSS, or latency.
