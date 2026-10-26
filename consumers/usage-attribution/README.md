# Usage attribution: supplied-snapshot consumer

**Source-reviewed example; all 37 Rust tests remain uncompiled/unrun.** This package has no accepted runtime CI, installation or Core transport result. See [validation status](VALIDATION.md).

This is an app-side stdin consumer, **not a Proteus tool module**. It groups a supplied `SessionUsageSnapshot` by Direct/Auxiliary origin, requested provider/model and recorded status. It neither collects usage nor reads journals, calls a provider, estimates prices, enforces budgets or grants permission. Do not register it as a module export.

The unchanged Rust dependency is `proteus-contracts` at Core-repository commit `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`, with a supplied lockfile. No Core runtime or module SDK is linked by this manifest. Relevant snapshot/projection source comparisons at `1fc3ef223d10322815dd9290a50d045bc95402bb` are source evidence, not current-Core interoperability testing. [Exact source analysis](SOURCE-ANALYSIS.md) and [pins](source-pins.json).

## What it answers

“Which recorded exchanges have known token counters, and which remain unknown?” The seven-exchange authored fixture has six groups, four usage-present rows and three missing-usage rows. Its 1,150 known input +230 output tokens are a **known subset**, not total spend or audited billing. The expected fixture report is supplied for exact comparison.

After a separately authorized, successful build and validation, the executable interface is:

```sh
usage-attribution-stdin < fixtures/mixed-snapshot.json
```

That command is documentation, not a run performed for this source-only package. It accepts stdin only, not paths or arbitrary transport envelopes. JSON `null` means unavailable, not empty/zero usage. Repeating a snapshot does not accumulate usage. The caller must obtain and authorize the source payload; deserialization does not authenticate it.

## Important limits

- One recorded exchange is not one HTTP attempt; hidden provider retries and owner identity are not inferred.
- Requested model is not proof of serving model. Repeated model IDs do not establish fallback lineage.
- Missing usage remains unknown. Optional reasoning/cache counts use all group exchanges as denominator and are not added again to input/output totals.
- There is no pricing table, currency cost, invoice, latency benchmark, generic evidence receipt or admission decision.
- Input is bounded to 8 MiB, rows to 4,096, provider/model names to 512 UTF-8 bytes each, and serialized output to 2 MiB including newline. A valid input can exceed the output limit; budget refusal emits no partial report. Ordinary OS stdout failure can still leave partial bytes.
- Duplicate exchange IDs and producer-inconsistent status combinations reject the input. Other request strings are not retained in the summary.

The 31 projection tests and six own-executable tests are authored but unrun. The stdio tests use blocking writes/waits and require an independently reviewed outer deadline and cleanup/resource envelope before execution. An experimental workflow and usage-specific supervisor profile are now authored in [ci](ci/README.md); their first hosted runtime is still pending. [Historical design notes](DESIGN.md). Those preserved design-stage notes include future-tense planning; current source/pin and unrun-runtime status are defined by this README, VALIDATION.md and source-pins.json, not those historical action items.
