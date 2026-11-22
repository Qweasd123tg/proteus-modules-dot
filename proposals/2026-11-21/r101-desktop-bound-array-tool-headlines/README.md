# Bound the Desktop tool headline for array arguments

For Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 through Desktop #423. Use `source.patch` on stock and `cumulative.patch` on the cumulative stack. Both change only `src/tool_display/mod.rs` and use the same array renderer. The cumulative version reuses #323's scalar helper and keeps its singleton behavior.

Desktop used to collect every string in the array and build the complete joined headline before taking the first 300 Unicode scalars. It now builds the visible prefix directly. A plural subject such as `paths` still shows the first value followed by the exact ` +N` suffix, but counts the remaining strings only if a digit can fit. Nonplural arrays still join untrimmed string entries with one space. Nulls and other nonstrings are ignored; empty strings still count. Key selection, full details, path-list quoting, approval-display fallback, execution policy and application limits are unchanged.

## Verification

- Checked the sealed M150 tree, 51 predecessor patches, and 14 locked dependency identities. Both variants applied and reversed cleanly and passed rustfmt and whitespace checks.
- Eight fresh focused Cargo test binaries passed: **12/12** tests each on stock and **14/14** each on cumulative, with an ordinary sorted JSON map and an insertion-order JSON map. For each map mode, the **2,043** complete serialized observation records matched byte-for-byte across stock and cumulative baseline/candidate. They include all headline fields, full path-list previews, other argument rows and the exact approval-body function over inert synthetic DTOs. The two modes correctly differ on fallback key order. Cases cover CRLF, lone CR, escapes, whitespace and empty/mixed/singleton arrays, UTF-8, combining and astral scalars, and partial count suffixes. Approval decisions and actions were not executed.
- Allocator requests at the actual `headline` boundary, on already built JSON; no timing, parsing or native view work included:

| Fixture | Requests, before → after | Requested bytes, before → after |
| --- | ---: | ---: |
| 2 paths | 5 → 3 | 240 → 75 |
| 8 paths | 6 → 3 | 368 → 75 |
| 20 paths | 8 → 3 | 1,136 → 76 |
| Short custom joined subject | 8 → 8 | 467 → 207 |
| Unicode plural cutoff | 9 → 3 | 4,598 → 920 |
| Synthetic oversized joined suffix | 8 → 6 | 198,741 → 2,417 |

The first three fixtures use the stock batch-reader shape with normal path counts. The oversized fixture measures only formatter work and does not assert that such an input passes any upstream limit. Summed allocation sizes are not peak or retained memory. Non-array control allocator counts were unchanged within each tier. No native GUI, full build, latency or RSS claim.

## Reproduce

Check `sha256sum -c SHA256SUMS` and run `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS`. Use `--run` only with the existing warm Cargo cache/target and common build lock (`CARGO_HOME`, `CARGO_TARGET_DIR`, `R101_BUILD_LOCK`, `R101_RAW_CARGO_DIR`). The runner uses locked offline Cargo with one job and checks the disk floors and growth fence. `python3 summarize.py RAW_CARGO_DIR EXISTING_RESULT_DIR` verifies the complete private traces and ordinary-batch allocator results. The package includes safe synthetic trace samples and hashes, not the multi-megabyte raw traces or source paths from Cargo JSON.
