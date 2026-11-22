# Skip runtime revision walks in the Desktop catalog

Applies to Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 through Desktop #425.

On initial catalog open and when installation status refreshes, Desktop needs the extension's ID, folder and any manifest error. It used to compute a recursive fingerprint of every valid package tree and then discard it. The catalog now asks for a distinct presence record from the same validated discovery scan. Runtime discovery still computes the same fingerprints at the same point. Root enumeration, manifest reads and validation, checks of packaged instruction paths, the treatment of user overrides and broken packages, module detection, and catalog refresh publication are unchanged. No cache or new install path is introduced.

## Verified scope

The packet verifies the sealed Desktop and Extensions inputs, all 52 Desktop predecessor hashes, and 125 dependency identities. Four separately compiled, fresh Cargo-selected tests passed **23/23** each, pinned and cumulative, before and after. The checker includes the exact manifest parser, manifest/inventory tests and production inventory, with the fixture's subset of the GPUI icon enum. Nothing launched an extension, backend process, or GUI.

The ordinary fixture reads the **14 complete sealed extension source-package folders**. All 14 catalog results and all runtime fingerprints matched across the four arms. Source-site counts for the ordinary inventory went from:

| Work | Before | After |
| --- | ---: | ---: |
| Manifest loads | 14 | 14 |
| Package revision calculations | 14 | 0 |
| Recursive revision directory reads | 41 | 0 |
| Revision entry metadata probes | 152 | 0 |

The native runtime discovery control still did 14 revisions, 41 recursive directory reads and 152 metadata probes. The synthetic override fixture also dropped only runtime revision work from inventory, while preserving the diagnostics and package paths. It covers same-ID files and links, valid and broken user overrides, dangling links, packaged instruction containment, invalid folders and module presence/errors. A new visible nested asset with an unchanged manifest altered the runtime revision but not the inventory; root-level hidden/cache additions changed neither revision nor inventory. All five observed output records matched byte-for-byte in a shared workspace. The fingerprint values themselves are path and metadata dependent.

These counts measure instrumented production call sites, not kernel syscalls, cold launch latency, general startup or total file I/O. Manifest loads and path checks still run. No full-app, elapsed-time or memory claim.

## Reproduce

Run `sha256sum -c SHA256SUMS`, then `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` for the sealed source, dependency, patch apply/reverse and formatting checks. The focused execution is `--run` with the existing warm `CARGO_HOME` / `CARGO_TARGET_DIR`, common `R103_BUILD_LOCK` and a fresh private `R103_RAW_CARGO_DIR`. It uses locked offline Cargo with one job and the disk floors/growth fence. `python3 summarize.py RAW_CARGO_DIR EXISTING_OUTPUT_DIR` checks parity, exact test receipts and both work controls without rerunning the executables.
