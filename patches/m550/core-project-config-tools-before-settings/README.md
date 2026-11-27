# Narrow the live tool snapshot before composing session settings

Standalone Core source patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. First verify `sha256sum -c SHA256SUMS` and `git apply --check /path/to/source.patch` in the detached Core checkout. The capture hunk has asymmetric common context so the same patch also applies and reverses on the exact tested earlier source selection through #939 including #927/#933. Only one application is needed.

Keep the fresh, ordered tool-registry capture at the same point, then project it to the existing registered-tool summary data before waiting for session settings. Reuse that data for display text and the structured response. The same live registry and labels are used; schemas/metadata are still materialized at capture, but are not retained across the await. Config-file reading and all admission/execution logic are unchanged.

Native validation: **103 tests per arm**, including session-model and HTTP tests. Exact summary text plus structured data bytes matched across three synthetic capture fixtures. The rich fixture includes long nested schemas/metadata, five provenance and safety variants, multilingual text, empty and multiline descriptions.

| Tools | Live bytes at the pre-settings boundary: stock → patched | Peak over the isolated probe: stock → patched |
|---:|---:|---:|
| 0 | 0 → 0 | 868 → 868 |
| 5 | 3810 → 858 | 5517 → 4370 |
| 128 | 1086345 → 21587 | 1113588 → 1099697 |

These are live requested allocations measured in a synchronous fixture, not a suspended application request, startup timing, whole-process memory, or RSS/PSS. Output is unchanged; the peak at the initial capture may remain. Exact runner and fixtures are embedded in the receipt.
