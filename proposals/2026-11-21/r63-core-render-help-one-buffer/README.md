# Core: render slash-command help into one exact-sized string

Exact base: Proteus-harness/Proteus-core `32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f`.

The `/help` response already has a validated, sorted command catalog. The old
render arm created one formatted string per command, collected them in a
temporary vector and joined them into the response. The new local renderer
counts UTF-8 bytes and writes the same text directly into one allocation.

Catalog discovery, sort, duplicate/reserved-name checks, argument validation,
chosen command dispatch and response wrapper are unchanged. Empty arguments keep
their original two spaces before the dash. Existing text is neither trimmed nor
normalized, and no terminal newline is added. Scope is the display branch only;
no config, transport, authorization, or runtime behavior changed.

All 100 Milestone 100 patch bodies and later Core source patches were checked
for command-renderer overlap. GitHub selected command/help terms returned the
unrelated dispatch/peer-settlement #27/#87, not this renderer change.

## Evidence

The isolated optimized Rust probe extracted both exact match arms and the
candidate helper, using the real stock Contracts DTO. Three tests passed in two
runs with identical results. The 516 byte-identical outputs include the exact
upstream builtin descriptors, mixed tool/profile commands, empty input, long
descriptions, Unicode, NUL, CRLF and other separator edge cases. The paired
runner verifies exact output length and capacity.

| Catalog | Allocation/reallocation requests | Requested bytes |
| --- | ---: | ---: |
| Actual eight builtins | 23 → 1 | 1,766 → 601 |
| Eight builtins + two fixture commands | 29 → 1 | 2,084 → 675 |
| Synthetic 64 entries | 142 → 1 | 6,994 → 1,818 |
| One long UTF-8 description/argument | 6 → 1 | 110,683 → 38,923 |
| Empty | 0 → 0 | 0 → 0 |

Measurement covers rendering only, including the final output string, with
fixture/catalog creation and comparison excluded. This is allocator request
traffic including realloc's new size, not CPU, latency, retained heap or RSS.

## Reproduce

With an exact clean Core checkout, its unchanged `proteus_contracts` rlib (built
by the same compiler), sibling dependency artifacts and `rustc`/`ld.lld` on PATH:

    git -C "$clean_core" apply --check "$packet/source.patch"
    python3 "$packet/probe.py" "$clean_core" --contracts-rlib "$stock_contracts_rlib"

Pinned source blobs, contract artifact hash, formatting, reverse byte
restoration and apply-only compatibility over Milestone 100 plus eight later
Core patches were verified. Full Core Cargo tests and the CLI, HTTP and stdio
route tests were not run under the shared build limit. No remote writes.
