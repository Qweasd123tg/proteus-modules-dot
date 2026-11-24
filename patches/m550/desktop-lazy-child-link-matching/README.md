# Desktop: don't decode a child link solely to rule out a missing overlay

One M384 production selector in `src/transcript/subagent.rs`, preimage
`7948cd74d6daa6858edd9d3233ad613a9f0b917a`, postimage
`55636a826ac00a9d334e9e3940308e84aaeb3c8d`. Prior Desktop selectors
#597 (both), #602, #609 (both), #613, #616, #621 and #624 apply/reverse
exactly. This selector commutes with that whole suffix.

On saved Proteus history, Core's durable task projection embeds a typed child
binding in the card without a live child-progress row. Row visibility and footer
look-ahead both call `progress_row`, which previously materialized the owned child
path before it could learn there was no overlay for that child. Only look up the
owned typed binding when there is first a same-child overlay candidate. Actual
navigation still validates and materializes the link. Compatible duplicates are
still resolved in display order, and an explicitly malformed binding never
suppresses a card, including when an overlay exists but is unbound. Legacy missing
and null references still match the first same-child overlay. Nonabsolute paths
and unknown/invalid typed fields remain rejected. No UI rows, caps, disclosed
state, or policy settings change. An explicitly malformed binding with no
compatible child now visits candidates first and skips decoding; no improvement
is claimed for malformed input or for overall scan complexity.

## Native paired replay

`verify.py` uses exact blob-pinned native implementations: Core's tool row/result
projection, journal binding finish and final 50-row page construction, the typed
page's JSON roundtrip, and Desktop's saved-history model apply, row-layout,
`stamp::hidden`, `stamp::turn_end`, `affected_rows`, and `task_session`. The
independent per-arm Cargo packages prevent accidental cross-arm binary reuse.
History source, request/finish route and callback order are authenticated in the
capsule. Fixture records and viewport are supplied in the harness. The test does
not run actual HTTP, a real journal session or GPUI.

Both default and preserve-order JSON layouts pass 36 tests per arm. The
50,000-row fixture yields a 50-row page in each scenario:

| Visible model case | Child cards | Typed binding decodes / allocator requests, stock -> candidate | Requested bytes, stock -> candidate |
| --- | ---: | ---: | ---: |
| Mixed, first visible tail subset of 20 rows | 8 | 24 -> 8 | 2,016 -> 672 |
| Task-heavy stress, 50 shown rows | 40 | 115 -> 40 | 9,660 -> 3,360 |

The confirmed valid navigable cards, row identities, turn boundaries, footer
timestamps, affected ranges, clipped edge decisions and output signatures
remain equal. The retained rows and page payload are unchanged. Counts scope
only the native row/footnote/link model with 84-byte synthetic paths, not the
50k GPU draw, process peak RSS/PSS, or user-reported timings.

With Rust 1.95 and the pinned registry closure in Cargo.lock:
`sha256sum -c SHA256SUMS`; `python3 verify.py --vendor /path/to/vendor`.
