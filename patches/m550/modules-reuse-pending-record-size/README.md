# Modules: reuse the exact size of a budget-deferred canonical record

In strict `ReadRecords`, a row inspected after the previous small result has
already passed the exact compact JSON byte count and the maximum-record check
before it becomes the pending row. Bringing that same owned object into the
next page used to perform the count again. The pending slot now carries the
already proven count with that one immutable record. A terminal row captured
during warm authentication explicitly has no count and still measures it
when exposed.

The size is not a cache keyed by a session or sequence, and cannot survive
dropping the pending object. All cursor resets, rewind, warm validation and
source-version logic remain unchanged. The existing maximum check still
runs. Initial counting, errors, decode, underlying reads, source proof,
return limits, and frame validation are not moved or relaxed. The separate
`ReadDisplayRecords` private stage path carries its own staged sizes and is
unchanged. This patch does not evict pending record memory, change the
worker protocol/encoding, or overlap Desktop #621 history scheduling.

**Exact base.** Full Modules M380 (610 files, modes and bytes), reconstructed
from M376 + exact #622 (which follows #618). Archive SHA-256
`47853afd9ae1bae7d14187d2d669b5e622bea186703a1b3aa6abaec719feaf24`, tree
`01dff7bfe0680458496b25f8be1b95ddc96f90c1`. One product file
`storage/session-storage/src/snapshot.rs`. Independent complete forward and
inverse checks give post-tree `6d61b71782c749fd774c06ae4ca6f110c39694f7`.
The product lock and pinned SDK `0c1b7572313230e5d123e95c722e1258a2e9ecd6` remain
unchanged.

**Native service gates.** Four distinct actual pinned Rust 1.95.0
session-storage tests, both serde_json map layouts before/after. 105 tests
passed per binary, including all 100 existing tests and five new tests:
exact nominal cap vs +1; eager maximum-size and malformed serialization
rejection before returning the prior small page; authenticated warm terminal
captured without rescan and still measured; ordinary retry/reset/reposition
and an interleaved read without stale count transfer; and fixed-prefix
corruption that cannot disclose the pending row even after a previous
successful page. Strict scoped maximum fixture passes at exactly 65 MiB
and rejects at 65 MiB +1. Two ignored entries include the prior test and
the separately invoked same-corpus large case.

**Actual work counted.** Real JSONL and SQLite canonical service,
one shared committed no-model fixture per backend: a tiny first record,
a 50,000-message x5 Append (37,389,295 compact canonical bytes), and
a distinct short tail. The projected 32 MiB cap still falls back.
Each combination reports the same page contents/order/wire digest, fixed
source fingerprint and decoded/read metrics. Stock counts the large row
in both page 1 and page 2. Candidate counts it in page 1, consumes exactly
that count in page 2 and continues to size the fresh tail; the same tail
does not get counted a second time on page 3. Each monotonic three-page
walk avoids 37,389,970 bytes of repeated compact serializer work
(37,389,295 + 675), not bytes from disk or bytes omitted from the response.

An independent actual M380 Core broker/old-SDK worker gate covered
three fixtures per layout (12 total before/after executions): exact
4 MiB, +1, and a true 50k no-model Replace with canonical fallback,
including fault, same-handle retry, and suffix fences. All paired
record cuts and digests match. A separate negative control shows
why removing the decoded staged owner by seeking back is held:
it can change the timing of later file-read errors.

This is a counted serializer workload and semantics result, not a
claim about whole-product duration, RSS/PSS, or releasing pending memory.

**Reproduce.** Only `source.patch` is the product diff. With pinned Rust
1.95.0 and a verified vendor directory:

    python3 proof.py --modules /path/to/Modules-M380-source.tar.gz \
      --core /path/to/pinned-Core.tar.gz --vendor /path/to/vendor \
      --work /path/to/new-work --target /path/to/new-target --prepare-only

Omit `--prepare-only` to build paired native test crates, seed the
synthetic fixture once and run all exact checks. The captured source and
mode builds used verified existing pinned SDK dependency artifacts and
fresh, different test binaries; the portable builder prevents stale
same-name reuse. The captured test-only spy counts just the existing
`ReadRecords` page size operation, not any other SDK serialization.
