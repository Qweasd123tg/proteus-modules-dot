# Core: release decoded history rows as cold rendering consumes them

The file-backed causal transcript scan initially owns a decoded
`HistoryMutated::Append` record. It already transferred suitable singleton
text into rendered rows, but iteration by mutable reference kept every
CanonicalPart Vec, unused owned metadata, hidden data and copied donor
buffers alive until all messages in the mutation were rendered. Consume the
same Vec by value and release each completed row naturally. The Vec iterator
still owns the outer slots while iterating. No extra allocation, pass,
validation exception, representation, rendering decision or storage/cursor
change is introduced. Timestamps still consume the entire record before the
loop. The live-turn skip, part deduplication, staged EOF/count guard, fallback
renderer, full fallback transcript and immutable publication all stay intact.

This runs during staged causal rendering, before the distinct #603 canonical
conversation write-to-display-write ownership gap. It is not #569 (existing
exact-capacity text move), #588 (later prefix scan row release) or a change
to the fallback renderer. Projected storage and strict validation can both
lead to this staged renderer; a later non-causal renderer remains unaffected.

## Evidence

Source applies after authenticated M350 + #599/#600/#603/#604 (order matters
for #604 after #600). Independent complete M362 archive and staged 1,099
files match exactly by path, mode and bytes. Both forward and reverse replay
were strict. The only product behavior change is the ownership loop; the
other patch hunk adds a native source test for Unicode/plain/blank/mixed
reasoning and hidden scope display parity.

The native test lift executes the real read/strict validation or display
projection, Core spool and renderer, presented prefix/cache pages and
fallback/HEAD/cursor path. The only substituted external boundary is a
typed in-process SessionStorage adapter with fixed synthetic data and injected
failures. Production dependencies `proteus-contracts` and
`proteus-session-semantics` are built from exact composed M362 and linked
into both arms with the frozen registry versions; no historical crate donor.
The generator makes only shown visibility/import glue and test-only probes.
The A/B checks 58 case/fault and two multi-record chronology/active-turn cases
per JSON feature mode, plus two 50k × 4 text cases in each. Stale/named errors,
late stage count or prefix errors, and returned pages/bytes, timestamps,
scope/roles/full-versus-tail result, source-bound cache and operation trace
are compared. The full Core workspace/real provider/GUI suite was not run.

The allocator witness records exact stage owner addresses/actual requested
layouts with allocation generations and checks the real display string
owners separately. These snapshots are internal liveness witnesses, not
process peak/PSS/RSS or measured latency. The original already transfers all
19,688,890 text bytes in the 50k fixture; text bytes and current rendered
row allocations were the same in both arms. The outer message slots are
unchanged throughout iteration and are released at the loop end in the
candidate, not on each row. Results on both projected and strict fallback arms (50,000 seeded rows,
one staged mutation; exact requested bytes):

| Phase / owner | Stock → candidate, default | Stock → candidate, preserve_order |
|---|---:|---:|
| Decoded parts before first row | 32,000,000 → 32,000,000 | 40,000,000 → 40,000,000 |
| Decoded parts halfway | 32,000,000 → 16,000,000 | 40,000,000 → 20,000,000 |
| Decoded parts before final row | 32,000,000 → 640 | 40,000,000 → 800 |
| Outer decoded slots before final row | 8,388,608 → 8,388,608 | 11,010,048 → 11,010,048 |
| Parts + outer slots at loop exit | 40,388,608 → 0 | 51,010,048 → 0 |

This is the original staged decoder's separately allocated nested parts Vecs,
not the validated canonical conversation owned elsewhere. The input decoder
and earlier allocations are not improved by this patch. The changed lifetime may matter for a peak
during rendering, but the previously reported 695 MiB is still unattributed.

## Reproduce

In a disposable checkout, independently materialize exact M362 (see receipt
and wave's composed source archive). Place it under `m362/`, replicate the
`changed/` after-images by applying `source.patch` to a separate copy, and
use the supplied generator input files. The complete workspace-relative
verification uses Rust 1.95.0 and the verified local vendor directory.
`build.sh` and `run.sh` build release/locked and execute both arms under
both JSON map layouts. The resulting JSONL control and scale logs are
bundled without test binaries.
