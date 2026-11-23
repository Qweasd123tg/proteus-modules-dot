# Build large display-prefix Base64 fields without a full raw buffer

Exact base: [Proteus-core at b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14), `crates/proteus-core/src/core/session_store/remote/view/prefix/packed.rs`.

The existing path stays in place for up to 48 records. For larger fields, encode 48 records at a time from a stack buffer into the final output allocation. Each full batch is divisible by three bytes, so only the last partial batch can emit padding. The completed bytes become the output string without a second allocation. Record order, format, source and resource preflights, decoder, and all callers are unchanged. A correct/incorrect record-count hint does not change the encoded bytes. The measured production widths use at most 1,536 bytes of raw batch scratch.

```sh
git apply --check /path/to/source.patch
git apply /path/to/source.patch
```

Against exact [#566](https://github.com/Qweasd123tg/proteus-modules-dot/pull/566), both unmodified patches apply and reverse in both orders with ordinary Git. When #566 is first, this hunk moves by 16 lines. The preflight and write path from #566 are unchanged outside the pack helper. No full serialization, worker, or Core application was run.

## Reproduce

Use the exact source inputs in `SOURCE-PROVENANCE.json`, saving each under the key plus `.ref`. The proof uses the official Base64 0.22.1 crate archive, verifies it against the actual Core lock, and tests it offline with the embedded isolated lock. Put the archive in `DEPS/archives` and its extracted directory in `DEPS/vendor`, using the Cargo directory-source `.cargo-checksum.json` with the verified archive hash and each regular file's hash. The existing R257 verified folder has this shape.

```sh
python3 -B proof.py --refs /path/to/refs --work /path/to/private/scratch \
  --rustc /path/to/pinned/rustc --cargo /path/to/pinned/cargo --deps /path/to/DEPS
```

Rust 1.95 compares exact Base64 bytes and reverse decode at widths 16, 17, and 32, including boundary record counts and mismatched hints. At 50,000 records the scoped helper avoids one raw allocation per call: 800,000, 850,000 or 1,600,000 requested bytes depending on width. These are independent calls, not a summed peak. Small-case allocations are unchanged. This is not an OS memory, cold launch, or product latency measurement.

The throughput test uses warmed, interleaved, seeded-order release pairs. It measures each width at 47, 48, and 49 separately, plus small, medium, 50,000-record and five-field workloads. The first exact wall-clock attempt tripped the small width-16 p90 guard despite a 1.019 paired median. The one follow-up used threefold longer windows, a separate fixed CPU and both wall time and process CPU time. The same median, p90 and order-split median limits apply to both instruments. The reported p10/p90 values are order statistics of the paired ratios, not confidence bounds.

The follow-up passed both rounds for all 22 cohorts on both clocks. Across widths and rounds, paired wall-clock medians at 47, 48 and 49 records ranged from 0.993–1.001, 0.981–1.015 and 0.946–0.998 respectively. The largest wall p90 was 1.239 (17-byte width, 48 records). The largest stock-first/candidate-first median on either instrument was 1.0212. This clears the scoped regression screen; it is not a statistical equivalence or product speed claim. The full per-cohort, per-order dispersion is in the provenance.
