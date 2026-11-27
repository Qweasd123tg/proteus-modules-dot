# Borrow configured model pairs when listing options

Standalone Core source patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify with `sha256sum -c SHA256SUMS` and `git apply --check /path/to/source.patch` in the stated detached Core checkout. Exact prior source selection through #938 (including #927 and #933) also applies and reverses.

The list reads only model and provider. Reuse the profile strings for duplicate detection, and own the pair only when appending it. Keep the existing active-selection branch and raw pair/order semantics. Model execution, live catalog requests, and reasoning selection are unchanged.

Native release validation: **103 tests per arm** including focused option generation, session models and HTTP. Complete ordered JSON results match on all seven cases. The Codex case uses the checked-in profile as shipped; synthetic alias duplicates exercise more load than typical.

| Case | Configured aliases | Output pairs | Allocation requests before → after | Requested bytes before → after |
|---|---:|---:|---:|---:|
| codex | 1 | 1 | 7 → 4 | 254 → 223 |
| empty | 0 | 0 | 1 → 1 | 72 → 72 |
| active | 134 | 5 | 407 → 13 | 3421 → 627 |
| space | 134 | 5 | 407 → 13 | 3426 → 627 |
| missing | 134 | 5 | 406 → 14 | 3572 → 783 |
| blank | 134 | 5 | 405 → 13 | 3472 → 683 |
| inactive | 134 | 5 | 405 → 13 | 3472 → 683 |

Measured on the synchronous configured-model helper, not heap residency, GUI startup, a provider call, or process RAM. The receipt contains the exact fixture and runner.
