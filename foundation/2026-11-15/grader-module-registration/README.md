# Journal grader: module-registration boundary

Delivery-only candidate for known F1/P2 (PR85), not a new finding.

The patch targets Proteus-harness/Proteus-core at bcbda4435534a296c707a1daa250813d692f68e1. It consolidates two dynamic-import sites into one helper: register before execution, restore the exact prior binding on failure. Production delta: +13 lines. Upstream Core/Modules and historical scores are unchanged.

## Evidence and limits
- Recorded Python 3.12.14 controls: baseline two expected dataclass loader errors; candidate six passing synthetic tests.
- 19 grading assertions and 13 unaffected functions are AST-identical.
- Publication verification repeated seven source Git-blob/SHA256 checks, strict patch application and byte equality against the reviewed candidate.
- Not full pytest, regrading, benchmark, Python 3.13.9, or full pinned fixture assembly.
- No performance or LOC-reduction claim.

## Package boundary
REPORT and independent reviews are preserved verbatim with their original chronology. Their references to runtime/, RUN-TARGETS.py, before/, after/, original report hashes and previous design evidence refer to the private working evidence, not files shipped in this directory. Raw logs, machine paths, runner wrappers and full source snapshots are intentionally excluded. RUNTIME-RESULT.json is the recorded bounded outcome. SHA256SUMS.json covers the published bytes only.

Apply grader-module-registration.patch from an exact Core source checkout with git apply --check --whitespace=error before applying. The added grader_loaders.md and grader_loaders_test.py describe and implement the standalone controls.

Prior finding: https://github.com/Qweasd123tg/proteus-modules-dot/pull/85
