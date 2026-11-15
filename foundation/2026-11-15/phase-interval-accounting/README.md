# Whole-observed-interval attribution candidate

Bounded follow-up to [known CPU P2, PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85), not a new finding. See [REPORT](REPORT.md), [patch](phase-interval-accounting.patch), [source review](SOURCE-REVIEW.md) and [runtime evidence review](RUNTIME-REVIEW.md).

This delivery repository stores a proposal, not an applied upstream change. Core base: `bcbda4435534a296c707a1daa250813d692f68e1`. Seven new synthetic tests and three selected existing controls passed; the raw baseline has two expected assertion failures. No real workload, Rust build, historical benchmark regeneration or PR126–128 rerun.

## Publication scope

Original report/reviews are preserved byte-for-byte. Their references to raw runtime logs, private execution wrappers, snapshots, CONTRACT-REVIEW.md, PRIOR-CPU.md and other local evidence describe the reviewed working package, not files included in this public subset. Raw logs, local environment paths, private wrappers and source snapshots are intentionally omitted. [VALIDATION.json](VALIDATION.json) records publication checks; [SHA256.json](SHA256.json) identifies the exact published files. The independent reviews distinguish source acceptance from inspected execution evidence.

Older saved subject aggregates stay unchanged with a warning. Old raw full-tree intervals without start provenance render CPU unknown (`н/д`), while retaining memory. No claim about correctness or recalculation of historical scores is made. Production code grows by 61 lines: the gain is one explicit shared invariant, not LOC or performance reduction.
