# Modules M391: verify an older warm prefix without building unused views

A genuine incremental Core transcript update calls `RemoteJournalSnapshot::scan_selected_after`, which sends `CompareSnapshots` before reading an append-only suffix. On the slow canonical comparison (older unremembered boundary or a provisional warm snapshot descriptor), Modules verifies the complete source and replays the requested older section to reconstruct its revision. It previously also produced model-context and usage views that the boolean response never uses. Call the existing validation-only fold at that one site.

The actual `JournalValidationState` still observes the exact same records in the exact same order with the same history, sequence, duplicate and lifecycle rules. Unchanged backend-specific fingerprint checks precede the same complete canonical replay; protected suffix content still gets decoded. Mismatch/short circuit, snapshot handle release, cached authenticated previous boundary, cursor/reset, error precedence and warm request validation do not change. Dedicated `ReadUsage` and `ReadConversation` still produce their complete views. No dispatch, SDK, lock, transport, public DTO or durable write changes. This is the distinct `CompareSnapshots` route, not #605's `ReadRecords` fold or #631's cache reply.

## Observed scope

- Exact full Modules M391 (610 files, pre-tree `4f97edfb6299859d75bd8d1eb3abde154b67d672`), pinned historical old SDK rev `0c1b7572313230e5d123e95c722e1258a2e9ecd6`. Four native test binaries with both `serde_json` map layouts. Each: 100 existing storage tests pass, two intentionally ignored including the separately run sidecar; each actual stock/candidate worker passes two durable restart/ambiguous ACK process tests.
- Shared durable older prefix: 513 records, 128 model turns with real success/error lifecycle, released prefix handle; new head at 519 with history and model facts. Three actual warm comparisons per backend per layout per arm (24 operations); same JSONL 1,038 and SQLite 519 decoded rows, exact boolean result, wrong revision and hash rejected, independent usage and context at the new head immutable. Same-length JSONL suffix corruption after both handles exist fails twice without exposing the prefix, then exact restoration allows the same comparison to succeed. Existing tests also exercise external blob damage and immediate verified boundaries.
- Full warm-operation allocator requested bytes showed nonoverlapping stock/candidate sample ranges in each route. Median comparison: default JSONL **−91,612 B**, default SQLite **−53,796 B**, ordered JSONL **−54,380 B**, ordered SQLite **−89,776 B**. Median allocation event count falls 384–410 across the four routes. Hash-map allocations naturally vary between folds; the test reports each sample. Diagnostics separately establish no decode reductions. These are scoped allocations for the operation, not wall latency, PSS/RSS, whole-product memory, or measured storage traffic.
- The genuine old SDK worker is driven over its actual stdio wire in legacy and display-capable host initialization modes, both backends and maps. Entire result frames match in each A/B except substitution of the newly generated snapshot UUID in opener and suffix pages. Releasing the old handle doesn't weaken the fixed-prefix comparison. Following suffix exposure returns six exact records including the model lifecycle; rewinding after another compare, wrong hash/revision, releasing the target, and unchanged usage/model context all match.

## Reproduce locally

```sh
python3 proof.py --modules <exact Modules-M391-source.tar.gz> \
  --core <r271/deps/source-archives/Core.tar.gz> --vendor <r274/deps/vendor> \
  --work <new-work-directory> --target <new-cargo-target> \
  --cargo <rust-1.95.0-bin/cargo> --rustc <rust-1.95.0-bin/rustc>
```

Use `--prepare-only` for source archive, vendored-registry and exact inverse verification without building. The test sidecar is appended only to ephemeral test source, not to the production patch. Recorded run rebuilt local exact native library test and candidate worker binaries from pinned native dependencies without network. The previously compiled W9 candidate worker is the exact accepted M391 stock binary; its recorded link pins and identical source tree establish baseline provenance. The packet is local only; no publication/release implied.
