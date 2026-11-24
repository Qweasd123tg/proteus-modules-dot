# SDK unit and allocation-generation proof

`source.patch` is the sole product change. The SDK decides whether the request is a blob read after the existing negotiation and validation gates. It still calls the storage backend exactly once. The candidate serializes the same typed BlobData response, with an empty placeholder owned by the temporary response, and replaces its pre-existing top-level JSON value in place. That preserves key order even with serde_json/preserve_order. If the placeholder cannot be found as an empty string, or shell serialization errors, the original donor is restored and standard serde_json::to_value is used. Empty and spare-capacity strings, other response variants, and responses to other operations are not donated.

`run_sdk.py` uses the exact staged worker inputs and offline vendor. It copies the input arms, attaches the unit overlay under cfg(test), and adds the already-pinned process-host dev edge for the SDK. It does not alter any registry identity, original manifest, or live production branch. Each test binary must be built fresh from the stated source paths; there are separate stock/candidate binaries for default and preserve_order. See the worker input receipt for lock and source provenance.

The common unit tests exercise the actual export method, including validation, error propagation, unmatched request/response controls, raw serde bytes, and `validate_response` for expected blob reads. The forced-shell candidate-only test feeds an error, no object, a missing slot, a non-string slot, and a nonempty string through the actual production helper's restore/fallback branch. These are test-only failure injections, not assertions that the pinned Serde produces unexpected shells.

The custom provider and tracking allocator validate that the response Value holds the same allocation **generation**, not merely an address, for exact-capacity reads with 1 and 4 independently held results. They cover length+1 capacity, substantial spare capacity, a 4-byte result from a >2 MiB donor, an empty result from that donor, unrelated PutBlob/ReadCache replies, and a genuine ReadMetadata string value. No result from a spare-capacity donor retains the unused capacity. The existing `ModuleTransport::write` is also exercised with a paused flush on the same execution thread and its real counting and writing code. The meter only covers Rust allocation/reallocation requests of at least 128 KiB in that thread. It does not measure process memory, transport framing in the real worker, or real blob encoding/IO; those are separate driver and worker-instrumentation gates.

## Verified release result

Both map modes yield matched targeted results. Each mode passed all five SDK unit tests in stock and all six in candidate (the extra forced-shell test exists only in candidate). For the 262,148-byte compact encoded payload, both read operations show 2 → 1 tracked requests and 524,296 → 262,148 peak bytes for one result. With four held results, tracked requests fall from 8 to 4 and peak from 1,310,740 to 1,048,592 bytes, with 1,048,592 bytes held in both arms. A paused flush holds 262,148 bytes in both arms without another payload-sized allocation. Every 1/4-result run returns to zero tracked bytes after drop. The spare/empty/unrelated controls show no donation or large-capacity retention change.

From a successful `replay_worker.py` run with work directory `/path/to/worker-replay`:

```sh
python3 -B run_sdk.py --stock /path/to/worker-replay/native/stock \
  --candidate /path/to/worker-replay/native/candidate --work /fresh/sdk-work \
  --vendor /path/to/worker-replay/vendor --toolchain /path/to/rust/bin \
  --target /path/to/worker-replay/target
```
