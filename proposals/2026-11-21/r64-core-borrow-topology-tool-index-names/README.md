# Core: borrow names in topology tool indexes

Exact base: Proteus-harness/Proteus-core `32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f`.

The tools projection builds two temporary sorted sets to report configured names
missing from the registered tool inventory. Those indexes now hold `&str` into
the immutable input; the values in the resulting tools DTO and warnings remain
owned. String and borrowed string ordering compare the same text, so sorted unique
warnings, stable ties in the sorted tool rows, and prior warning order remain
unchanged. No registry, runtime management, safety/policy, or renderer changes.

This is the topology DTO producer, not #365's output renderer. The 100 M100
patch bodies and nine later Core patches had no overlap in this projection.
Targeted GitHub search found #365 only for the generic borrow/topology pair.

## Evidence

The exact full `topology/tools.rs` module and its existing unit test compiled on
each side with real stock Core `AppConfig`, Contracts DTOs, and the unchanged
private ownership classifier linked/extracted from the same pin. Each of two
runs passed 5/5 tests (the existing test per side and three probe tests).

196 byte-identical paired serialized payloads include actual tool rows, schema,
source, process owner, flags and warnings. Fixtures cover duplicate/empty
names, Unicode, stable sorted ties, existing warnings, missing names and all
source variants. A specific assertion verifies deduplicated warning order.

| Synthetic projection | Allocation/reallocation requests | Requested bytes |
| --- | ---: | ---: |
| Empty | 0 → 0 | 0 → 0 |
| 16 registered and 16 configured | 309 → 277 | 25,235 → 24,323 |
| Duplicate and Unicode names | 143 → 129 | 11,397 → 11,091 |
| 64 registered and 80 configured | 1,278 → 1,134 | 116,924 → 113,548 |

Only the synchronous projection is counted. Fixture construction, payload
comparison/serialization, configuration discovery and downstream renderer are
excluded. Successful allocator requests include realloc's new size; no
CPU, latency, RSS/PSS, peak or whole-application claim.

## Reproduce

Use a clean pinned Core checkout and matching locked rlibs and native
dependency directory from one stock target. Compiler and artifact hashes
are in `gates.log`; have `rustc` and `ld.lld` on PATH.

    git -C "$clean_core" apply --check "$packet/source.patch"
    python3 "$packet/probe.py" "$clean_core" \
      --core-rlib "$stock_core_rlib" --contracts-rlib "$stock_contracts_rlib" \
      --serde-json-rlib "$stock_serde_json_rlib" --native-dir "$native_lib_dir"

Pinned preimages, apply/restore, formatting, and read-only cumulative
application onto M100 plus nine later Core patches passed. Full Core,
CLI/HTTP and cumulative runtime were not run under shared build limits.
No remote writes.
