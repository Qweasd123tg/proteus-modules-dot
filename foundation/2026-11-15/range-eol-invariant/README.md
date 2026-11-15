# Ranged-read EOL invariant: source-only proposal

Remediation of the known CRLF ranged-read → literal-edit mismatch, not a new finding. Preserve actual separators between selected unnumbered lines with +6 production lines; omit the last terminator as before. Numbered output remains LF. No arbitrary round-trip guarantee.

## Choose one patch alternative

- `range-eol.patch`: apply to Modules `c035142558f0fca43e9772fc0e50ca293abf1531` without PR119.
- `range-eol-on-PR119.patch`: apply only after [PR119](https://github.com/Qweasd123tg/proteus-modules-dot/pull/119)'s `bounded-read-utf8.patch` on that base. Do not apply both EOL alternatives. The original patches conflict in either order.
- [PR116](https://github.com/Qweasd123tg/proteus-modules-dot/pull/116) changes direct_patch, not this file-tools boundary. Three placements around PR119 + its EOL alternative produce byte-identical trees in text-only checks.

## Evidence and status

Read REPORT.md for exact limits, RANGE-EOL-INDEPENDENT-REVIEW.md for independent source review, SOURCES.json for pinned identities, and VERIFICATION.json / MEASUREMENTS.json for checks and size. Patch bytes are unchanged from independent review. Published report wording was adjusted only to match the sanitized package; source snapshots and raw logs are intentionally excluded.

Both alternatives passed isolated `git apply --check --whitespace=error` and exact applied-file comparison. Twelve source Git blob hashes were independently recomputed for publication. Five proposed Rust tests are **NOT RUN**. No compilation, runtime or CI pass is claimed. Merge here publishes evidence only, not a production fix; upstream code, dependency pins and binaries remain unchanged.
