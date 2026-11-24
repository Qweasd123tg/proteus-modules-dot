# Core: seek the latest protected cache tail after one manifest check

## Change
Page loads through HEAD or an explicitly named immutable revision now keep a private immutable CheckedHeader. It can only be constructed by the existing full header validation (session/metadata and **all three** sections, including byte/row/hash/pack-span limits); named revision validation and live source rechecks still run at their existing boundaries. Carrying this evidence avoids rescanning the selected transcript manifest in the page decoder. Unchecked raw sections, full-model reads, append and save paths retain their existing checks.

A verified protected latest tail cannot contain a packed span. For ranges beginning in the final at-most-50 rows, seek backward from the validated row total until the first overlapping logical leaf, then use the same forward content decoder. All requested leaf hashes, type/count checks, actual packed-byte caps and typed deserializations remain. Older ranges still take the original forward pack traversal. Empty, out-of-bounds, malformed or moved-source cases fail as before. No fewer physical reads, no new cache schema, no check against a stale or unvalidated header bypassed.

## Evidence
Exact M411 Core source (M404 plus accepted #650/#653), all 1,101 paths match the canonical modes/sizes/blob inventory; candidate reverses cleanly. Native actual selected startup/paging/validation code uses a typed in-process Storage boundary. In both serde_json layouts and both 50,000-row startup paths (projected ×4 and strict ×5), the initial named page now structurally checks 2,000 manifest entries instead of 3,000, and the forward locator visits 1 instead of 1,000 logical leaves, with one additional reverse step. Same physical key/order and response bytes. On a maximum-length synthetic structural manifest (65,536 leaves, not an actual 3.28M-row journal), forward entries 65,536→1 plus one reverse step, structural checks 131,082→65,546 including the small conversation section.

Both layouts match 135 paired route controls, including 34 paging-specific cases, plus reciprocal packed prefix readers. Explicit one-row-earlier historical range still reads the required packed object, a >4 MiB singleton creates multiple tail leaves and keeps exact order, absent/unknown/wrong-source header and forged page checks preserved. Signed valid metadata with malformed non-viewed conversation still rejects. Changed source on the second latest-page fence rejects. The 65,537th leaf over the cap still misses before body reads.

Counters cover actual PageRef entry visits in the selected algorithms. The full header still parses and validates all of its metadata, and the leaf work and broker I/O remain. No latency, PSS, full-process start or cross-release claim.

## Replay
Materialize m411 from the authenticated M404 archive plus #650 and #653 as described by integration. Run python3 seal-source.py; python3 proof/generate.py orig; python3 proof/generate.py new; ./run-route.sh; ./run-certs.sh; python3 compare.py; python3 seal-proof.py. The native scripts enforce the 300 MiB temp space floor and reuse the pinned offline dependencies.

Native proof retained separately, SHA-256: `460f74abb612abaf54b468255ebda0c2e12711fd1c2dcba39ff5492b8ef6315c`.
