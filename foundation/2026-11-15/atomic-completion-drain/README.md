# Atomic completion drain: source-only proposal

Status: **uncompiled, unexecuted candidate**, not a delivered production fix.

[Report](REPORT.md) · [Patch](atomic-completion-drain.patch) · [Independent review](ATOMIC-WAIT-INDEPENDENT-REVIEW.md) · [Source identities](SOURCES.json)

Replace two check-then-drain sites with the owned result of the existing atomic drain. Production source: **1075 → 1067 lines (−8)**; no new framework, helper, lock or dependency.

The old interleaving requires a genuinely concurrent thread consumer. Normal serial workflow incidence is not proven. The proposed contract test may pass baseline and does not reproduce the original cross-thread window.

[PR118 delivery HOLD](https://github.com/Qweasd123tg/proteus-modules-dot/pull/118) remains open: this does not add delivery acknowledgements, replay or budget-aware delivery.

Verification: independent source review; ten baseline blob identities rechecked; fresh Core/Modules refs unchanged; git apply --check --whitespace=error and text application verified against expected after bytes. Compiler, formatter, tests, runtime, provider calls and full candidate-stack composition were **NOT RUN**. No performance measurements. Merging this artifact package is not upstream integration.
