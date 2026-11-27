# Skip a workflow-call index when no replayed response can use it

Standalone Core `source.patch` is for `024fb944a91382026bb2aa5c7b8da65c284d0305`. With the overlapping selected Core patches including #926 and #937, use only `after-dot937.patch` on the exact listed prior tree `1be49edcd4138af504bb4a6f5ca843f6b9ce3546`. Verify checksums and use Git apply --check. These are mutually exclusive selectors for one change.

The first pass detects whether any successful model response at/after the visible replay frontier has an explicit tool-call list. Only then collect workflow call IDs over the complete prefix. Existing root/owner checks, nested display eligibility, order, reset, dates, and validation remain intact. The separate part-commit condition is unchanged. Unlike #937, this avoids **building** the unused set; do not sum the two isolated savings.

Native validation: **151 transcript/HTTP tests in each of four arms**. The four ordered JSON outputs were byte-identical in all arms. Both positive fixtures still populated the index (normal late workflow evidence and a historical-record shape with explicit tool calls but no message parts).

| Source comparison | 4,096 requested-only insertions: before → after | Live requested bytes at end of pass 2: before → after |
|---|---:|---:|
| standalone | 4096 → 0 | 623048 → 311736 |
| prior selection with #937 | 4096 → 0 | 623048 → 311736 |

Role/phase checks are conservative: nested or non-live outcomes can keep construction enabled, but no required response loses evidence. Scoped probe only, no app PSS, startup timing, or full product verification. Exact reproduction dependencies and metrics in receipt.
