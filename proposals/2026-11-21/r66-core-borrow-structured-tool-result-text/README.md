# Core Contracts: borrow structured tool-result text during display joins

Exact base: Proteus-harness/Proteus-core `32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f`.

`ToolResult::text_or_status()` already returns an owned display string. When
it falls back to structured content, it no longer clones each nonempty text
part into the temporary join list. The list borrows those strings and owns only
the formatted JSON/media entries. No wire type or input changes.

Nonempty error still wins over nonempty output, followed by structured
content and the same status fallback. Empty text parts are skipped, other
whitespace is retained, JSON uses the same serializer, media data stays
out of the label, and part order and separators are unchanged.

This is the shared text projection, not the consumer-side excerpt or terminal
metadata patches (#241/#265/#312) or #78's retained preview prefix.

## Evidence

Twice, 11/11 isolated Rust tests passed: the four existing `domain/tool.rs`
tests on each exact full module, plus three paired tests. There were
864 byte-identical serialized DTO and display-text pairs, also checked against
the genuine stock Contracts library. Fixtures cover mixed payloads,
success/error precedence, empty data, Unicode/whitespace/control characters,
nested JSON, and unchanged opaque metadata.

| Synthetic input | Allocation/reallocation requests | Requested bytes |
| --- | ---: | ---: |
| Empty / status | 1 → 1 | 11 → 11 |
| Nonempty plain output | 1 → 1 | 13 → 13 |
| Single structured text | 3 → 2 | 122 → 109 |
| Mixed structured text, JSON, media | 7 → 5 | 242 → 226 |
| JSON only | 4 → 4 | 132 → 132 |
| 64 KiB UTF-8 text plus short tail | 4 → 2 | 131,215 → 65,656 |

The allocator counts the synchronous display call, including its output
string. DTO construction and wire serialization are excluded. Requested bytes
include realloc's new size; no retained-heap, RSS, CPU, latency or whole-turn
claim. Full Contracts/Core, live app routes, and combined runtime were not run.

## Reproduce

Use a clean exact Core checkout and actual locked rlibs from one stock
dependency directory built by the same compiler. Artifact hashes and
compiler are in `gates.log`. Keep `rustc` and `ld.lld` on PATH.

    git -C "$clean_core" apply --check "$packet/source.patch"
    python3 "$packet/probe.py" "$clean_core" \
      --contracts-rlib "$stock_contracts" --serde-rlib "$stock_serde" \
      --serde-json-rlib "$stock_serde_json"

Pinned source, exact forward/reverse byte restoration, formatting,
and apply-only compatibility on M100 plus eleven later Core patches passed.
No remote writes.
