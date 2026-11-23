# Core: release the previous display header during a cold cache rebuild

**Only `source.patch` changes production code.** It changes one function, `remote/view/cache.rs::save_model`, on [Core b2d2e6de](https://github.com/Proteus-harness/Proteus-core/blob/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14/crates/proteus-core/src/core/session_store/remote/view/cache.rs#L353-L400).

A readable HEAD normally serves the saved view without invoking this writer, even when stale. But HEAD can still be well-formed while its latest physical transcript leaf is absent or corrupt. In that case the saved-view read misses; the rebuilt model is then saved and the writer validates HEAD again to calculate a possible common prefix. The old conversation/context manifests and tool index have no use at that point.

The patch keeps the full header validation, then moves out only the previous source and transcript manifest. Other fields drop **before the first page is built**. The prefix comparison consumes those remaining owners, so they drop **before tool indexing**. No new clones, preflight reads, partial decoding, altered hash checks, or changed write/publish order. No difference is expected when there is no valid prior header.

## Measured ownership, not process memory

The following are **bytes from actual tracked allocations of the deserialized prior header no longer live at that phase**, relative to stock. They are not bytes avoided over the run. Both implementations release all tracked owners by return.

| Prior archive | First new page / first pending pack | Entering tool indexing |
|---|---:|---:|
| Real emitted archive: 200 rows, four pages per section; rebuild 200 rows | 1,164 B | 1,761 B |
| Real emitted archive: 5,000 rows, 100 pages per section; rebuild 5,000 rows | 22,380 B | 34,209 B |
| Synthetic 1,000-page-per-section header; rebuild 200 rows | 242,860 B | 381,569 B |

The last case repeats references to real immutable leaves/packs in a structurally validated header. It exercises deserialization and ownership of long manifests, **not a replay of 50,000 distinct rows**. The first two cases use all three real writers for both generations, with distinct typed canonical messages, rendered transcript rows and context observations. The first-generation tool map has one entry. Actual gains depend on the session shape and how often this recovery path runs.

At first page submit (after materialization, before the pending-pack call), the current 50-row page encoded to 13,291 B. Its **simultaneously live** array buffers and nested strings/keys accounted for at least 12,140 B under the default JSON map, or 16,140 B under `preserve_order`. At the first retained pack frame the current page/frame buffers tracked by the gauge were at least 13,196 B or 17,172 B, respectively. These two current-byte observations overlap; do not add them or subtract them from the table. No claim about total allocation volume, process peak, RSS/PSS, cache-hit frequency or end-to-end startup latency.

## What was exercised

* The compiled lift calls the upstream `PreparedSession::from_dir` and `into_display_view`, real `load_saved_view`, real `project_validated_view`, `save_model`, named revision lookup and page reader. The model at the validated-read/render boundary is fixture input, not a native replay of a disk journal. The in-memory storage transport handles the actual typed cache requests, checks session/source identity and records the request and response bytes. Context summary estimation is a fixed fixture boundary. The real typed canonical DTO is restricted to its used `Text` content variant; transcript rows, sections, packs, hash functions, prefix encoding, tool writes and publication run as lifted from Core.
* Warm (including stale but readable) HEAD bypasses rebuild. No HEAD and an invalid **unselected context manifest** cause misses without a validated previous owner. With an intact valid HEAD and a missing or wrong-hash latest body, the real saved read fails and the prepared path rebuilds. If the replacement page is identical, the writer restores its key and the base records the full common prefix. If the new tail differs and old body is still absent/corrupt, there is no base. If an earlier packed page differs and is readable, the precise common-prefix index is kept.
* Independent failure injection covers an unreadable old comparison pack, current page or tool write, optional prefix write, named revision write and HEAD write. Optional prefix failure **does not** fail publication. Named write failure may leave the prefix; HEAD failure may leave both prefix and the new named revision. All 15 cases compare the ordered request/response bytes (or injected error), exact final cache contents, and returned views / operation results across all four arms. No fail-atomic or rollback guarantee is inferred for the cache.
* A single-threaded native allocator observer registers the original `String` / `Vec` bases and capacity sizes on a borrow of the validated prior header; the borrow does not move or clone it. It records the **first** deallocation or successful reallocation of each generation and checks its actual layout. Reuse of an address cannot revive an owner. Probes run with the first current page and first pending pack alive, at entry to tool indexing, and after the caller returns. The old transcript hash/page/pack buffers and source strings remain live at first page in both arms; only the candidate has released them by tool indexing. The measured non-transcript group includes previous conversation/context page and pack arrays and hash strings, tool keys/values, preview, prefix and cursor strings. No map-node internals, untracked usage fields, allocator slack, or backing store residency are added to the figures.

## Composition and replay

The verifier checks 27 pinned Core source inputs, SHA-256 for all 38 official crate archives against both lockfiles, and Linux x86-64 Rust 1.95.0 tool hashes. It applies and reverses all six permutations of R267 plus [#571's cold-model release](https://github.com/Qweasd123tg/proteus-modules-dot/blob/3cf600e6ed9c121199d3ee2959c3ff80ecdd222a/patches/core-release-cold-model-before-named-page-read/source.patch) and [#574's borrowed tool projection](https://github.com/Qweasd123tg/proteus-modules-dot/blob/6e729e61801613ab1a41d16ad10fc74b7ea1d9f3/patches/core-borrow-tool-index-arguments/source.patch). All eight possible patch subsets yield the expected module blobs independent of order. The two `composition-*.patch` files are exact test inputs, not prerequisites for applying this production patch.

Four native arms are compared: stock, R267 alone, #571+#574 without R267, and all three. Both serde_json map layouts are built and exercised in debug and release. The lifetime receipts match between stock and the composed baseline and between the candidate alone and the three-patch result. This verifies the exact affected source slices, not a whole workspace build or an installed application. System C build tools are required for ring but are not hash-pinned.

A separate source-only cross-check of the overlapping `cache.rs` hunks from [#566](https://github.com/Qweasd123tg/proteus-modules-dot/pull/566), #574, and R267 produced `b73a394a42cad878ac097fcca45bb6b7c5c76fc4` in all six orders and reversed to stock. This is not a native #566 composition result; #566 is not one of the four executable arms.

From this packet directory with a read-only official Core checkout and existing official crate archives:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --source /checkout/Proteus-core \
  --work /fresh/private/work --toolchain-bin /path/to/rust-1.95.0/bin \
  --archives /path/to/official-crate-archives
```

Repeat `--archives` for multiple archive directories. See `SOURCE-PROVENANCE.json` for immutable input/postimage IDs, and `verification.json` for the observed per-build receipts.
