# Count durable rows instead of cloning them for compaction

Exact base: [Proteus-modules at 331cfc20](https://github.com/Proteus-harness/Proteus-modules/tree/331cfc20bbaf821ab07de49868426da29ebdeb64), `hook/codex-context-preparation/src/{history,compaction,remote}.rs`. Core SDK lock: `0c1b7572313230e5d123e95c722e1258a2e9ecd6`.

The shared history split keeps its existing summary and ephemeral-context copies. Instead of making a second owning collection of durable messages, it counts them at the same branch. Both compaction routes select users from the unchanged input using the existing predicate. That predicate rejects request-only rows before extracting any text, so evaluating it on the input preserves user selection, order and content. Zero durable rows still return the original unchanged output. Durable history with no real users still compacts. The existing requests, budgets, output diagnostics and mapping are unchanged.

## Apply

On stock, use `source.patch`. If exact [#563](https://github.com/Qweasd123tg/proteus-modules-dot/pull/563) is already applied, use `composed.patch` **instead**. Ordinary Git rejects the raw pair in either order because the adjacent diagnostic line is patch context. The carrier changes exactly the same product lines; it does not loosen the source-context checks. The proof also regenerates the complementary exact #563 carrier for the reverse application order.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

With the appropriate carrier, all 120 orders of R255 and the exact four prior patches (#517, #521, #562 and #563) converge byte-for-byte and reverse every intermediate tree. All used ordinary private `git apply`, not three-way resolution or stripped context.

## Verification

Use the pinned inputs in `SOURCE-PROVENANCE.json` named by each reproduction key plus `.ref`.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc
```

Rust 1.95 passed 14/14 in debug and optimized modes. Source-bound proof includes the actual history split and selectors, and the local/remote decision and allocation paths across four source tiers. It covers 4,096 generated cases per mode, empty or request-only history, durable history with no users, mixed part scopes, durable and request-only tool pairs, duplicated IDs, and mock failure/cancellation. Provider requests, estimate services, UUID randomness, and JSON are inert inputs. No actual provider, Cargo integration or application was run. The three changed files pass rustfmt standalone and composed.

In the synthetic split-only fixture, a 131,072-byte Assistant text and a 262,151-byte tool output each go from two matching allocation requests to one. The 4,093-byte ephemeral text still requests two. Total allocation requests were 17 to 11, no reallocations, and summed requested bytes 797,142 to 403,080 in both build modes and source tiers. Input setup is outside the meter. These are not peak memory, process PSS, startup or latency results.
