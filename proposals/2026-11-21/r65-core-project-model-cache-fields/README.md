# Core: copy only requested model descriptor fields

Exact base: Proteus-harness/Proteus-core `32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f`.

The process model's capabilities and hosted-tools getters each need one owned
field. The previous descriptor cache cloned the whole description for either
getter, including unused schemas. The same cache now clones only the requested
field; on a miss the original checked descriptor is moved into the cache.

Provider/model cache keys, order of the broker call and adapter-ID check,
reset and error behavior, descriptor lifetime, and returned DTO ownership
remain unchanged. No broker operation is moved under the lock. No new
wire field, validation rule or cache was introduced.

M100 and the ten later Core source patches had no overlap with this model adapter
or descriptor helper. Targeted GitHub searches found no same candidate.

## Evidence

Three focused Rust tests passed twice. The executable compiles the exact two
getters and cache function from the base and candidate against real locked
Contracts DTOs. A scripted client supplies typed descriptions for miss/error
cases, not real broker integration. 96 byte-identical traces cover 960 getter
calls with warm hits, cold misses, repeat reads, distinct provider/model keys,
the same wrong-identity error and reset, transport failure and final cache
contents. Modifying returned nested values does not mutate cached data.

| Warm getter fixture | Allocation/reallocation requests | Requested bytes |
| --- | ---: | ---: |
| Text-only capabilities | 3 → 2 | 26 → 13 |
| Text-only hosted tools | 3 → 2 | 26 → 13 |
| One hosted tool, capabilities | 21 → 3 | 1,491 → 14 |
| One hosted tool, hosted tools | 21 → 19 | 1,491 → 1,477 |
| Oversized schema, capabilities | 21 → 3 | 50,631 → 14 |
| Oversized schema, hosted tools | 21 → 19 | 50,631 → 50,617 |

Evidence counts successful allocation requests including realloc's new size
for a single warm synchronous getter. Setup, comparison, cache creation
and transport are outside measurement. No broker calls occurred during the
measured hits. This does not claim CPU, latency, RSS, peak, or model turn memory.

## Reproduce

Use a clean pinned checkout and the same compiler as the genuine locked
stock rlibs; place `rustc` and `ld.lld` on PATH. Compiler and artifact checksums
are in `gates.log`.

    git -C "$clean_core" apply --check "$packet/source.patch"
    python3 "$packet/probe.py" "$clean_core" \
      --contracts-rlib "$stock_contracts" --serde-json-rlib "$stock_serde_json" \
      --anyhow-rlib "$stock_anyhow"

Exact apply/reverse, formatting, and M100 plus ten later Core patches apply-only
passed. Full Core and actual worker-process integration were not rerun for this
candidate under shared build limits. No remote writes.
