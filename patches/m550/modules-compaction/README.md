# Modules: avoid retaining an extra copy of local users during compaction

Local compaction previously filtered and cloned *all* eligible users, then selected
from that collection backwards. Walk the borrowed original slice backwards and
apply the same eligibility check after the remaining-budget guard. This avoids
cloning the old prefix and does not even classify it after the budget is exhausted.
It does **not** remove the original history from the summary-model request. The
remote retention path, summary ordering, exact budget, truncation and ID mapping are
unchanged. Eligibility is a pure predicate that neither obtains IDs nor mutates
messages. Its only observable outputs are classifications. The retained suffix
is still cloned where required by the output contract.

**Base:** complete M350 Modules archive SHA256
`a04006ac24402104fc7366d6c41fd2090c7a8add508f28e0980522e0f98e70d1`, Git tree
`826088a9432dd024d7b1aa4ded490cb5608ff65f`. A second replay independently
reconstructed all 31 files in this hook from the historical source and exact
intersecting selectors #514, #517, #521, #525, #562, #563 and #564 (composed).
Two source paths, one user-retention change; root product lock unchanged.
Product diff is **source.patch only**. Apply from the Modules root with
`git apply --check source.patch` then `git apply source.patch`.

**Native verification:** Rust 1.95.0; both arms, default serde_json and separately
with preserve_order. 53 existing hook tests and one additional public
HookModule::invoke_json test passed in every arm. The only substituted boundary
is the model host (upstream TestHost); actual request serialization, dispatch,
summary result, recovery, DTO and production retention code are used. The focused
wire test uses 0/32/128 older 8 KiB users, request-scoped context, assistant,
generated/aborted users, a retained 79,996-byte user and a 4-byte UTF-8 user
at the exact 20k-token boundary. It checks output content, IDs/order, mapping,
summary diagnostics and that all original messages reach the host.

| 128 older users | Default before → after | preserve_order before → after |
|---|---:|---:|
| Allocations/reallocations | 3,906 → 3,127 | 3,911 → 3,132 |
| Total requested bytes | 13,825,252 → 11,396,772 | 13,961,240 → 11,507,240 |
| Peak net live bytes relative to wire entry | 8,246,710 → 7,064,566 | 8,336,206 → 7,138,622 |

The counter is thread-local around invoke_json, after serializing the input and
before parsing the returned JSON. Realloc charges its requested new size in total
bytes and only the size delta in live bytes. These are fixture-specific allocator
results, **not** whole-process RSS/PSS, startup or measured time. The baseline
and candidate still pay the cost of encoding/decoding the complete history.

**Reproduce:** unpack the M350 Modules archive and obtain Proteus-core at
`0c1b7572313230e5d123e95c722e1258a2e9ecd6` (Modules' pinned contract).
With Rust 1.95.0 and a verified vendor directory for the locked crates, run:

    python3 proof.py --modules /path/to/M350-Modules --core /path/to/Core \
      --vendor /path/to/cargo-vendor --work /path/to/new-directory

The portable Cargo entry point verifies all hook and SDK source SHA256s, checks
every registry resolution against the product lock and applies this exact patch.
It reproduces the default configuration. To verify source and dependency resolution
without allocating a new build target, append `--prepare-only`. The captured default
and preserve_order runs used native rustc test targets linked to the same pinned
SDK source and registry crates; rand 0.9.4 and its missing dependency archives
were checked against the product lock before compiling. More generally, allocator
sizes may differ across configurations. The portable proof asserts semantic
output and relative bounds rather than the recorded exact byte counts.
