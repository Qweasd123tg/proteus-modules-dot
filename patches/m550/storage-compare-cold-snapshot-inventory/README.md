# Compare, rather than recollect, the cold snapshot blob inventory

Cold `OpenSnapshot` still does its full initial inventory and strictly replays
the journal. During its subsequent validation, compare against the captured
stamps with the existing matcher instead of building a second full map.
A fresh filesystem walk, error handling, digest, and sidecar publication
checks are retained. This is distinct from #825's separate publication check.

Apply `source.patch` to exact Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`.
If #815 or #825 already applies, use **only** the corresponding exact alternate
embedded in `receipt.json`: `after_815`, `after_825`, or `after_815_825` (the last
expects #815 then the #815-specific #825 variant).

```sh
jq -r '.selection.after_815_825.patch_base64' receipt.json | base64 -d > source-after-815-825.patch
```

All eight matched optimized library builds and unmasked storage test suites
passed. The owned synthetic cold snapshot results and allocator counters for
each matching predecessor pair are in the receipt. They are not measurements
of physical disk reads, end-to-end latency or resident memory.
