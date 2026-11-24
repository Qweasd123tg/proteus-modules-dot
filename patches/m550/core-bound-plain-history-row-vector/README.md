# Core: smaller row owner for one certified large text append

Exact 1,100-file Core M395. The owner #618 report was read statically; none
of its scripts was run. Its first successful 50k GUI open had a 738.1 MiB
tree peak (Core 396 MiB at that sample), while a separate profiled process
attributed roughly 40 MiB live requested allocations to this specific
AppTranscriptMessage vector. Those two runs are not additive, and the
owner's release is not asserted to equal M395.

The change uses the existing fixed single staged text-only Append
certificate, with no extra scan or bytes on the wire. Such a record
can emit at most one display row per message, even with joined multipart
text, blanks or dedup. After filtering admits a row and growth is already
necessary, the last Vec growth reserves the smaller bounded ceiling
instead of doubling. It does not allocate the whole output upfront
while all decoded inputs still exist. Short, oversized, rich,
multi-record, non-staged and malformed cases retain normal checking and
geometry except temporary output in a count-failure case, which is still
discarded. Optional allocation refusal leaves ordinary Vec growth.
The same proof means no reasoning row can need earlier answer positions:
the otherwise populated assistant-answer HashMap is omitted only there.

This does **not** delete the full display transcript: canonical/cache
publication, previous prefix matching, exact cursor, latest 50 and full
named-page-failure fallback remain. No work is shifted to another process
or disk, and no source, renderer readiness, committed/staged EOF/count,
tool, page or authority check is removed.

## Native A/B

The production Core stage, renderer, cache, prefix and read routing are
compiled from exact source, against the authenticated typed Contracts and
native M395 Semantics. The adapter is in-process at the typed storage
boundary, not an installed worker/GUI. 74 pairs **per** JSON layout:
58 standard startup/cache failures; two strict frontier cases; three
strict Replace cases; two 50k scale fixtures; six large row-shape
controls (same power, blank-filtered, multipart, rich answer/reasoning,
late rehosted part, nonmatching live turn); three large failure/fallback
controls. The latter verify full 50k rows on named-page miss, full 8,193
rows on earlier page write failure, and a genuinely appended unexpected
stage record rejected at EOF with no cache publication.

Matched final-live allocations immediately before renderer finish
(one Core process, per 50,000-row route; row text and other owner groups
also compared). Default and preserve-order have different slot stride:

| JSON layout, same in projected and strict | Vec cap before → after | Vec requested bytes before → after | Separate populated answer index before → after |
| --- | ---: | ---: | ---: |
| Default, 520 B/slot | 65,536 → 50,000 | 34,078,720 → 26,000,000 | 819,216 → 0 B (25,000 entries → 0) |
| Preserve order, 640 B/slot | 65,536 → 50,000 | 41,943,040 → 32,000,000 | 819,216 → 0 B (25,000 entries → 0) |

At row 32,768 capacity was exactly 32,768 in both arms; at row 32,769
it diverged at the first inevitable large growth. The slot delta is
mostly allocator-requested spare capacity, not pages necessarily
touched or resident. Report the answer index separately as an actual
populated allocation. No RSS/PSS, whole-app latency, or extrapolation
to the owner's #618 observation.

## Explicitly unselected follow-up

The separate architecture note/small native witness demonstrates exact
public JSON serialization for 50k representative plain compact rows and
zero-copy text promotion while reducing the row stride to 80 bytes. It
is *only* a representation witness, not a patch or an integration
result: cache publication/pack/repair/page-failure fidelity and full
fallback latency still require testing. It is not included in source.patch
or counted separately.

Native proof retained separately, SHA-256: `c52b4d43acc1835ad9c6536937f526f8b968892626f9090392c25ad667a91536`. Compact representation not included in this patch.
