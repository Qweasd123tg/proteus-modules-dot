# Instruction source bootstrap proposal

Source-only continuation of known [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) profile-recovery finding #2, not a new defect or deployed fix.

One private source projection protects the two missing-standalone-profile writers from persisting loader-resolved file+text. Production change is **+13 net lines**, not a speed or size optimization.

- [Report and qualification limits](REPORT.md)
- [Exact candidate patch](instruction-bootstrap.patch)
- [Independent exact-patch review](SOURCE-REVIEW.md)
- [Earlier architecture review](INDEPENDENT-REVIEW.md)
- [Publication mechanical checks](PUBLICATION-CHECKS.json)

Three proposed Rust tests, compilation, formatter and server recovery: **NOT RUN**. Strict text application and all six orders with the exact #86 and #137 patches pass; that does not qualify combined behavior. Upstream Core is untouched.

This does not restore missing assets, include layout, comments or old malformed profiles, rebase references, or guarantee cold loading if an asset vanished. The assumption is loader-produced configuration recreated at its original standalone path.

The report's INITIAL-* artifacts and full source snapshots remain outside this delivery package; the initial registration-context conflict is disclosed in the report. Published references identify the exact external patches without duplicating them.
