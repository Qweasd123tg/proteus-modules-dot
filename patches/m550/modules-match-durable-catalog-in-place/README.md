# W17: avoid materializing a second blob-stamp map when opening a warm durable catalog

One-file local optimization against the exact M411 delivery Modules tree
`8eb580401e4af24d0fc665ba5a452db49427b425` (same authenticated archive as M400).
Independently reapplied and reversed on all 610 tracked paths. The postimage is
`4cc5824a807dd27558afebb4f5f6e00e90c6a0ec`. Original Rust Contracts, SDK, and
Semantics pin `0c1b7572313230e5d123e95c722e1258a2e9ecd6` unchanged. This is
separate from official Go and old W14–16 proofs. No external action, version
change, pin change, or Node.

A worker that loads the v1 durable storage catalog has already parsed one
map of expected payload path stamps. Instead of retaining/storing every
same newly observed stamp and pathname in another full map, the production
loader borrows the already sorted expected paths, reuses one relative-path
buffer per directory, and records the last matching outcome for known paths.
Unexpected keys are still tracked separately by their distinct paths so
the exact directory cap is respected. Stamp fields, symlink/metadata/error
checking, directory iteration, depth and distinct-path cap, serialized
data/checksum, source-version/fingerprint validation, catalog fallback, and
canonical journal I/O are unchanged.

Duplicate/churn argument: the raw walk has one distinct-path count and the
same traversal order. An existing key's later observation replaces its
previous equality state (matching or not), while an unexpected key can never
make the maps equal but still counts exactly once. No metadata branch is
short-circuited. Linux tests compare all 32,768 possible five-observation
traces in the alias/match/unexpected alphabet against exact BTreeMap insertion
at each prefix. Real trees check zero/missing/extra, exact 16,384 keys and
one over, 16-level directory traversal, a non-UTF8 filename and disallowed
symlink/type. Test-only sidecar is not in the production patch. 104 unit
tests passed in each layout, 1 pre-existing manual test ignored.

In the genuine native child `OpenSnapshot` loader, a valid 526-stamp packed
JSONL sidecar from one actual 50,000-message history hit durable metadata
rather than replaying. A same-binary serial ABBA with exact original
collector versus production comparator produced identical snapshot frames and
left the catalog bytes alone. In each serde layout, *blob matching only*:
2,705 → 1,068 Rust allocations/reallocations, 189,656 → 86,395 B cumulative
requested and 107,532 → 13,616 B maximum extra live requested bytes above
entry. Both variants return to entry live bytes. No-blob JSONL and SQLite
control each unchanged at 5 requests, 746 B requested, and 508 B peak.
Tests do not establish full load/snapshot peak, process PSS/RSS, speed, or
platform-specific behavior beyond the Linux test host. Invalid paths can
still allocate for tracking; only positive hits avoid the second stamp map.

Separate uninstrumented real legacy SDK workers matched canonical 50k
`OpenSnapshot → ReadRecords → ReleaseSnapshot` on JSONL/SQLite in both
layouts. Independent real typed host verified cache positive marker,
malformed sidecars, missing/stale sidecar entries, actual missing referenced blob
denial, symlink cache fallback, exact release/strict reads and durable bytes on
both backends (referenced external payload fault is JSONL only).

Build-input and QA scripts are retained with the evidence scope. Parent
workspace source staging and existing immutable historical fixtures are
required to replay the scripts. Logs documenting retirement of old unrelated
own Cargo scratch are kept; both actual official Go ELF files, authenticated
Git source, known locked registry archives and provenance were preserved.
