# Core: compact plain transcript owner through paged startup

Exact M398 includes #640; this is a separate change on top of its targeted
last-growth/index savings. The only new consumer is PreparedSession's
initial paged display view. One existing certified staged Append with
4,096–65,536 singleton text messages gets a compact private row owner.
It uses the existing timestamp proof, shared visibility/dedup and
capacity-aware text extraction. An extra bounded singleton-shape check
reads in-memory metadata only. No extra spool read, staged file, network
operation, budget change or public wire/schema change. Small, rich,
multipart, multi-record, nonstaged, or ordinary unpaged/HTTP paths keep
the existing full rows. Warm prepared startup still takes its page without
calling the renderer.

The same cache writer builds canonical/display/context leaves, prefix,
named revision, then HEAD. Compact rows implement the public row's
text-only JSON shape and field order. An older different leaf uses the
same typed common_prefix, and tool writes are provably absent for this
shape. No cache write happens before stage EOF/count and prefix checks
complete. Exact named page success returns the original 50 public rows
and cursor. On miss, at that same boundary, the complete verified compact
transcript promotes to public rows by moving each existing owned String.
No second render/read/storage request.

Promotion must allocate the public row Vec while the compact container
still exists, and allocate the public role strings; its time and
transient co-ownership are not presented as a win on misses. The canonical
message owner has already been released at that boundary (including
previous publication failures). The common successful branch never
allocates a whole public row vector.

## Verification

Actual selected native PreparedSession/startup/cache/renderer/stage/pack
and prefix path over typed in-process Storage. No unchecked source
constraints, synthetic wire exception or new worker flag. Exact forward/
reverse source replay on all 1,100 M398 files. A native compiled
wire+ownership test per serde layout compares to the real public typed row.

83 A/B cases per layout: 58 normal/fault controls, two strict frontier,
three strict Replace, two 50k cold opens, six large renderer-shape checks
(including actual rejection of compact when startup allows it but rows
are rich/rehosted or multipart), twelve extra cache/fallback checks.
The latter include an earlier different logical leaf (exact common
prefix 125 and old revision), staged trailing-record and late-prefix
failures before any cache publication; display, prefix, named and HEAD
write errors; corrupted named identity; full 50k named miss; large warm
and unpaged checks. All result, page/header/body hashes, immutable cursor,
request order, errors and stage checks match. Where promotion happens,
capture checks all existing rendered String allocation addresses agree
with the fallback's actual public rows, after the attempted named read.
Transport is a validated typed adapter, not installed worker/GUI.

## Requested live row owner

For each actual native cold 50k fixture (projected x4 and strict x5),
the whole rendered slot owner was:

| serde layout | Exact M398 before | Candidate after |
| --- | ---: | ---: |
| default | 26,000,000 B (50,000 × 520) | 5,242,880 B (65,536 × 80) |
| preserve order | 32,000,000 B (50,000 × 640) | 5,242,880 B (65,536 × 80) |

Measured at rendering end plus before conversation write, display
packing, and named-page probe. Retained text is separate; unchanged
canonical, prefix and other model owners are compared independently.
Most removed by-value full-slot storage held the complete 50,000
public structs with empty fields; this is not a second credit for
unused geometric capacity or the answer index eliminated in #640.
Requested live bytes are not whole-process RSS/PSS or installed-app
latency, and the owner #618 report is not rerun or extrapolated.

Native proof retained separately, SHA-256: `4c10d7f29ccd2fec2e94a30bad223d59cd0d2716da4211e3fc5ce5e5b0239263`.
