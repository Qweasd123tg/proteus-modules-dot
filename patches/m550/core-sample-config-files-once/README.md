# Use one fresh file-list observation per configuration summary

Standalone Core source patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. First verify `sha256sum -c SHA256SUMS` and `git apply --check /path/to/source.patch` in the detached Core checkout. This same narrow-context patch also applies and reverses on the exact tested earlier source selection through #940.

List diagnostic paths once immediately after session settings composition; reuse the same sorted display strings for text and JSON. Stable content is unchanged. Each request still reads current filesystem names and applies the same physical-inline resolution and top-level filter, without caching the assembly-time list. During parallel directory changes, both fields now share one observation rather than sampling twice; this is not an atomic disk snapshot. Profile loading is unchanged.

Native validation: **103 tests per arm**, including the actual local summary probe and HTTP tests. Exact normalized JSON (only disposable temp paths and session path replaced), including display text, matched on five cases. The directory fixture includes a symlink to a file, nonmatching extension and nested-directory exclusions.

| Input | Real config_files calls per summary: stock → patched | Diagnosed filenames |
|---|---:|---:|
| none | 2 → 1 | 0 |
| named | 2 → 1 | 1 |
| inline | 2 → 1 | 1 |
| directory | 2 → 1 | 3 |
| missing | 2 → 1 | 0 |

The measured count is helper invocations, not OS syscalls or milliseconds. In the directory case it removes the second traversal. None already performs no filesystem work. No provider catalog, external tools, GUI, or end-to-end performance claims. Exact runner and fixtures are in the receipt.
