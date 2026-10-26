# Validation: source-only, runtime pending

As of 2026-10-26, this candidate has source review, Rust1.95 formatting and an offline-generated Cargo.lock. Locked no-deps metadata and an integration-owned formatting check were recorded before a final test-only boundary addition; subsequent direct formatting checks covered the final source. These are not compilation or test results.

- **31 projection tests:** authored, uncompiled/unrun.
- **6 authored executable tests:** authored, uncompiled/unrun; they would exercise this stdin program, not live Core/AppServer transport.
- Fixture arithmetic and literal test-name/source consistency checks: separate static evidence, not substitutes for Rust execution.
- No upstream tests, live provider/network, benchmark, billing audit, deployment, CI run or PR exists for this package.

Exact expected names are in `expected-tests.json`; intended future validation must reject missing, duplicate, ignored, filtered or failed tests rather than rely only on a process exit or a summed count. Preserve per-target 31/6 summaries and exact fixture/diagnostic results.

The original source receipt is `245918721eceac1c822659228d58f84e60b8375f4772d0eee0a619a4c72af393`; source review receipt is `7bacfca63c3faad51707bdc455be344910f5627d404eaa57c8312bea5651d8e1`. Cargo.lock SHA256 is `76b87ea36b1577541eab5fd8be8e99695a96cb1a03c05caf29105e11c29e81d2`. Hashes identify local evidence, not publisher authentication or runtime acceptance.

This proposed public layout preserves all Rust, fixtures, lock, analysis, source pins and expected-test bytes. Only README/this validation note are adapted. A later independently reviewed workflow must use fresh bounded artifacts, source/binary before-after hashes, a mandatory outer stdio deadline and explicit direct-child cleanup evidence. The existing resource-envelope-v1 has **no usage profile**; do not silently borrow another package's settings.

`DESIGN.md` is deliberately preserved as historical design-stage context, including its original future-tense review/pinning steps. Those statements do not override the completed source comparisons or the still-unrun runtime status recorded here.
