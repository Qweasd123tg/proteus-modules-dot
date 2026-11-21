# Core: borrow topology render cells and labels

Exact base: Proteus-harness/Proteus-core `32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f`.

The topology table now gathers borrowed cells from the immutable snapshot, rather
than cloning the two active-slot strings or five tool cells per row. Source labels
already exist as static strings in `ModuleSourceTopology::kind()`. Use that accessor
in the table and Markdown, and borrow the same labels in the diagnostic map and
runtime path/Mermaid. The complete output string is still owned. No retained cache,
new dependency, DTO/API change, snapshot mutation, or runtime/security change.

Slot/tool order, identical first-match lookup, Rust char-based padding, and each
view's distinct absent/missing labels are preserved. Full Mermaid is unchanged.
Dedup: all 100 M100 patch bodies and recent Core packet paths inspected; no topology
renderer overlap. GitHub title/body search returned the separate #101 Mermaid
hook-order audit and unrelated #71/#235, not this ownership change.

## Focused evidence

Both complete exact renderer source sets compiled in one optimized isolated Rust
test executable against the existing real stock Core Contracts artifact. The probe
ran all six renderer tests from the repository on each side and three probe tests:
15 passed. 132 fixture snapshots give **792 byte-identical rendered outputs** across
table, map, runtime path, Markdown, runtime Mermaid and full Mermaid. Fixtures cover
ordinary/empty/large registries, Unicode/control characters, all source kinds, absent
selection, literal sentinel IDs, missing matches, duplicate modules and mixed slot
ordering; inputs were unchanged. Two completed runs produced the same corpus digest.

Ordinary synthetic fixture: eight slots and 16 tools, one complete synchronous render.

| Renderer | Allocation/reallocation requests | Requested bytes |
| --- | ---: | ---: |
| Table | 140 → 36 | 11,161 → 9,541 |
| Map | 296 → 280 | 26,178 → 26,068 |
| Runtime path | 47 → 43 | 4,541 → 4,514 |
| Markdown | 539 → 511 | 52,496 → 52,304 |
| Runtime Mermaid | 182 → 178 | 7,622 → 7,595 |
| Full Mermaid (control) | 320 → 320 | 17,049 → 17,049 |

The table removed 104 requests, exactly \(8 × 3 + 16 × 5\). The 64-tool stress
fixture measured 381 → 37 requests, 25,505 → 20,309 bytes. Scope is allocator
requests including realloc's new size and final output construction; the fixture,
serialization for parity, CLI arguments and HTTP transport are outside the measured
closure. This is not latency, retained heap, peak, RSS/PSS or whole-runtime evidence.

## Reproduce

Use an exact clean checkout and an unmodified `proteus_contracts` rlib from that
checkout, built with the same Rust compiler as the probe (prepared dependency libs
in its sibling dep directory). The existing locked stock artifact used here is
fingerprinted in `gates.log`. Keep `rustc` and `ld.lld` on PATH.

    git -C "$clean_core_checkout" apply --check "$packet/source.patch"
    python3 "$packet/probe.py" "$clean_core_checkout" --contracts-rlib "$stock_contracts_rlib"

`cargo fmt --all --check`, worktree diff checks, exact reverse restoration, and
read-only apply-check onto M100 plus the six R57–R60 Core patches passed.
The ordinary Core Cargo/official CLI and HTTP route suites were not rebuilt or
run for this round under shared compiler resource limits. No remote writes.
