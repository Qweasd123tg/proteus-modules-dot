# R291: Reuse the verified checkpoint carry message

One-file, independent production patch against Core
`b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`. Apply only `source.patch`;
everything else in this packet is validation material. The strict source
composition receipt covers recent patches through #593 with checked forward
application and reversal, not a combined runtime or upstream merge.

## What changes

A later checkpoint can keep the same pending call binding without acknowledging
an already captured result in its newly proposed prefix. The old code cloned the
raw result into a fresh canonical row, checked that row against the stored row
with full typed equality, discarded it, then built the same canonical row again.
The candidate moves the first verified row into the original insertion slot
when the raw call ID selects the same binding. Next-state and old/new binding
validation, proposed prefix copying, exact typed equality, guards, and mutation
order are left intact. The ordinary record helper still constructs lazily only
after the original checks have succeeded.

That last same-binding guard is necessary even though strict and live legitimate
callers produce matching capture rows. The public HistoryCapture caller can
craft a stored canonical row whose outer IDs belong to one binding while the
typed raw result points to another. For those cases, the prepared row is dropped
before the original record lookup, so unknown IDs still make no insertion,
another pending binding still gets its own IDs, and a duplicate still gives
the old error. No public function, cache format, caller, or persisted request
changes.

## Proof and reproduction

See the pre-run `GATES.md`, `route-scope.md`, and raw receipt files. The offline
lift uses actual Semantics, Contracts, and the exact no-store checkpoint caller
with pinned Tokio, both default and preserve_order Serde layouts. The strict
route starts from physical typed journal records; direct malformed helper
controls are labeled separately from reachable strict and live cases. The
selected owner witness requires both address identity and a still-live recorded
allocation generation; it does not assume different pointer addresses. Scopes
include only verified carry preparation and insertion; allocations for the
rest of the caller, message hashing, JSON, and unrelated work are excluded.
This is requested allocation Layout, not full-process heap high-water, time,
PSS, RSS, or a benefit on text-only startup.

Verify packet integrity with `sha256sum -c SHA256SUMS`.
Recheck native receipts with `python3 check_layout.py default.jsonl` and
`python3 check_layout.py preserve_order.jsonl`. For a portable offline replay
from the exact pinned Core inputs and a verified local archive store, inspect
`python3 proof.py --help`; `--action stage` validates required bytes without
compiling, and `--action run` builds, runs, and validates both layouts. No
remote operation is part of the proof.

## Observed results

Both layouts pass 102 paired cases (89 strict/live plus 13 direct helper cases),
including 44 matching intended carry observations, 54 route pairs without a
carry, and 33 protected strict/live rejections. All 18 large accepted route
pairs per layout meet the predeclared per-carry condition. The same output bytes
and capacities stay owned by the returned row, while the discarded complete
construction and its retirement disappear. At an 8 MiB body, each row below
is identical for the two measured routes within its layout:

| Measured body | Default bytes / requests avoided | preserve_order bytes / requests avoided |
| --- | ---: | ---: |
| Raw output | 8,390,292 / 14 | 8,389,956 / 16 |
| Raw error | 8,391,057 / 19 | 8,390,549 / 22 |
| Structured text, with structured content and metadata | 8,391,197 / 22 | 8,390,657 / 25 |

The extra bytes above the body length are the same selected construction's
nested and enclosing owners and scratch requests. The observed scoped net bytes
and the returned selected capacities do not decrease. A checkpoint failing
after one or more accepted local carries keeps its exact earlier error behavior;
no accepted durable/ACK benefit is inferred for the rejected checkpoint.

## Raw receipt transport

The complete original JSONL receipts and source-only composition receipt are stored as Base64-wrapped gzip. Decode them before invoking the checkers or reading the composition:

```sh
for name in default.jsonl preserve_order.jsonl composition-receipt.json; do
  base64 -d "$name.gz.b64" | gzip -dc > "$name"
done
sha256sum -c RAW-SHA256SUMS
```
