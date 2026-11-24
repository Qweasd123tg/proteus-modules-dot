# W22: move only compact large Opaque ciphertext leaves

Local M420 Modules optimization. One existing file, exact base
42d90c9875077980626b5d8676ab3e6de14ae594 and exact post-tree
053da7269e6f28841cf6bb8082747524fdf6575e. Independent forward and inverse over
all 610 paths; same legacy SDK/Contracts/Semantics pin 0c1b7572. W21 moving
all of Opaque.data is rejected because it retains more structural capacity.
This replaces that idea with a compact scalar leaf move; the W21 patch is
not a prerequisite and is not shipped.

Current actual M420 adapters establish two recognized shapes: OpenAI
Responses compaction's encrypted_content string and Anthropic's redacted
thinking data string. The candidate only takes that existing leaf when the
typed format and item discriminator match, valid UTF-8 length is at least
4096 bytes and the String capacity exactly equals its length. It serializes
all surrounding maps, arrays, tags, ordering and other contents via the
original DTO serializer. The string is moved into its already-emitted slot.
Unsupported formats, wrong or missing types, short values, over-capacity
strings, and any other fields go through exact old behavior. There is no
new data access, redaction, stage, verification, cap, SDK, host message or
compatibility negotiation. The second read is fully retained.

## Real native scope

Actual existing stock Linux workers committed 151 synthetic messages to the
real journal before reopening, using 144 synthetic provider-shaped encrypted
or redacted-thinking strings. No real provider response or secrets. All four
backend/serde map A/B arms preserve exact normalized output for projected
open, required display second read, full conversation, canonical strict
records and released-handle failure. JSONL durable bytes and SQLite
canonical logical stored rows unchanged. Exact cap succeeds, one byte
under emits no partial frame, and legacy negotiation stays exact. Same-size
late JSONL corruption after successful open still fails the second read
and the same handle can retry after restoration.

Per layout, 2 existing subprocess durability tests and a direct exact
ownership test pass. The latter checks 4,095/4,096, escaped Unicode byte
count, known and unknown type, empty/wrong/missing data, inflated string
capacity fallback, ordinary serialized container identity and actual
pointer transfer of the eligible string. Small ordinary-Text wire and
allocator controls are identical in all four pairs.

The same native instrumented binary ABBA scoped **only serde Value
construction, after storage returns and before SDK framing** eliminates
144 Rust allocation/reallocation requests and 3,146,112 cumulative
requested bytes per affected output in both layouts and backends.
Observed extra live high-water requested bytes:

| Mode | Open display | Second display page |
|---|---:|---:|
| default | 405,517 → 402,499 | 336,391 → 329,917 |
| preserve_order | 324,721 → 317,819 | 239,647 → 228,329 |

Final extra live requested bytes exactly match stock for every arm. These
numbers are not elapsed time, product RSS/PSS, or the owner's all-Text
50k workload. No Go/Windows/Node or external action. Dedicated sole compile
slot ended before running the bounded real worker comparisons; all three
disk samples met floor. No old files needed reclaiming; the reclamation
proof is read-only planning, not the result of a file action.
