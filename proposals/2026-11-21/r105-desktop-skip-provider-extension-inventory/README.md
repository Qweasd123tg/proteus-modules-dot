# Use module-only inventory for Desktop provider discovery

Applies to Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and the sealed M150 stack through Desktop #427.

Add connection and Providers metadata preparation use installed module paths, not extension status. The provider worker used to build the complete catalog inventory before reading those paths. It now uses the same backend resolver and module inventory scan, without reading extension manifests. The normal catalog still uses the complete inventory and shows broken overrides. Provider template validation, receipt precedence, order, program SHA-256 checks and byte input, authentication metadata and controls are unchanged. No cache or shorter validator was introduced.

## Focused evidence

- Verified 53 predecessor hashes, 132 locked dependency identities and the sealed Desktop and Extensions source trees. The one patch applies to both tiers. Four fresh Cargo-selected test executables passed **27/27** cases each, using the actual public provider discovery and the normal catalog inventory. Complete output traces matched byte-for-byte in the same workspace, including template fields, inert auth metadata and request construction, choice ordering and provenance, errors, and ordinary/broken user-override catalog status. The receipt-only case with a missing backend was also checked in each executable.
- On the **already-#427** stack, the worker stopped making **2 extension root scan attempts, 14 manifest loads**, and one each of the three packaged-instruction path checks on the fixture with the sealed 14-package source tree. All those counts fell to **zero**. The revision counters were already zero in that baseline, so this is work in addition to #427, not a recount of its saved tree walk. A broken user extension added another load on the baseline and none on the candidate. The normal catalog kept its scans, checks and lookup results in both cases.
- In the provider fixture, 9 module manifest reads in the provider validator, 6 program-open attempts, and all 106 bytes fed into SHA-256 still occurred, alongside the unchanged initial module inventory probes. The fixture exercises duplicate choices and overlapping receipts, malformed and oversized manifests, missing files, rejected paths, wrong and uppercase valid SHA-256, and a module that still appears as a provider even though shallow inventory marks it broken. Real file reads used inert bytes and an isolated fixture environment. No credential read, provider executable, authentication command, backend process, network or GUI was run.

These are counts at production call sites, not kernel syscall, cold-start, latency or memory results. There is no full-application build or runtime claim.

## Reproduce

Run `sha256sum -c SHA256SUMS` and `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` for static verification. Run `--run` with the existing warm `CARGO_HOME` and `CARGO_TARGET_DIR`, common `R105_BUILD_LOCK` and a fresh private `R105_RAW_CARGO_DIR`. The runner uses locked offline Cargo with one job and the shared disk floors and growth fence. `python3 summarize.py RAW_CARGO_DIR EXISTING_OUTPUT_DIR` confirms all exact matching traces and counter controls. Trace paths are anonymized; choice key hashes naturally depend on absolute fixture paths and can differ in another workspace.
