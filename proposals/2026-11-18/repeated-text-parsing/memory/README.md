# Resident memory: headless Markdown stream

The measured processes are the same release transport host and Markdown ELFs used for the non-instrumented timing series. The sampler verifies their SHA-256s against that run, selects the sole direct child by PPid, checks its actual executable, and verifies the final tree digest and expected sequence of delivered revisions after completion. Linux, CPU 4, four fresh-process pairs per workload, alternating AB/BA. This was a separate memory run, not a second source of latency data.

| 64 input offers | Validated replies | Baseline → candidate median sampled peak PSS of both processes |
|---|---:|---:|
| Growing 53,762-byte Markdown, ACK each | 64 | 10.87 → 10.68 MiB |
| Late reference definition, ACK each | 64 | 10.95 → 10.41 MiB |
| Late definition, all updates before first ACK | 2 | 8.72 → 8.79 MiB |

No general memory reduction established. The 0.19 MiB median difference in ordinary prose has overlapping run ranges, the late-reference sequential case varies substantially on the candidate, and the negative burst case does not improve. In the sequential late-reference case 63 early offers can take the alternative route; the last cannot. Four pairs, independent allocator conditions and non-continuous sampling are inadequate to attribute small changes conclusively.

Each sweep reads `Pss:` in KiB from the live host’s and then the live renderer’s `smaps_rollup`, takes their **sum in that sweep**, and the largest of those sums in the run. Timing between sweeps is approximately 1 ms plus reads; the two readings are **not atomic**. Observation covers the interval after locating the spawned renderer until the host's final stdout becomes readable or either process disappears. It includes any observed warmup/close/final hashing activity while both are alive; it is not a synchronized phase-specific allocation trace. The short burst had only 17–19 paired sweeps per run; short-lived peaks may have been missed. Core, GUI, GPU, filesystem cache and observer are not added. The raw [results](results.json) retain each per-run peak split, sample count and sweep duration.

```sh
python3 sample.py "$HOST" "$BEFORE_PACKAGES" "$AFTER_PACKAGES" "$FIXTURES" "$TIMING_RESULTS_JSON" --cpu "$CPU" > results.json
```
