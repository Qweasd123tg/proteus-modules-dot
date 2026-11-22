# Classify each Desktop config-picker entry once

For Proteus Desktop `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded` and sealed M150 through Desktop #429.

On opening the configuration picker, the worker enumerates entries and classifies their type. A normal profile used to be checked once as a directory and again as a regular file, both through filesystem metadata. Now the same symlink-following metadata result supplies both decisions. Lexical names, symlink following, canonical paths and deduplication, labels and metadata budgets, sorting, diagnostics and manual file selection all use the same paths as before. This equivalence is for a stable tree: a concurrent replacement might formerly have been observed differently by the two type checks. The patch does not add a freshness or security guarantee; the later canonicalization and open checks are unchanged.

## Focused result

- The one-file patch passed forward/reverse application, whitespace and formatting on stock and cumulative. Verified 54 predecessor hashes, 38 locked dependencies, and the sealed Desktop/Core sources. Four fresh Cargo-selected executables passed **10/10** tests each (the original catalog tests and three focused fixture tests). Their full ordered rows and diagnostics matched byte-for-byte.
- The ordinary fixture uses the **eight real profile files** from sealed Core under the portable installer's directory layout, including its helper profiles and an active Codex variant. Classification calls went from **19 to 11**. It still did **8 eligible file canonicalizations, 8 label opens and read 65,063 bytes of profile text**. No profile was launched and no config includes or providers were resolved.
- In a mixed file-type fixture, classification calls went **23 to 15**, with identical rows and other work. Lexical file and directory aliases, physical deduplication and current-row identity, a cycle, dangling/self-referential links, a character-device alias, malformed profile text, duplicate titles, ignored entries and config-named directories all keep their behavior. Directory/depth/entry limits and the total **8 MiB** label budget retained the same diagnostics and work outside the type check. The per-file label cap and the config count cap also passed the native catalog unit tests.

These are counts at production call sites, not a kernel syscall, latency, total I/O or app startup result. No GUI or full Desktop build ran.

## Reproduce

Run `sha256sum -c SHA256SUMS`, then `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS`. To run the exact launcher catalog in a headless harness, use `--run` with the existing warm `CARGO_HOME`, `CARGO_TARGET_DIR`, common `R107_BUILD_LOCK` and a fresh private `R107_RAW_CARGO_DIR`. The runner preserves locked offline Cargo, one job, the disk floors and the growth fence. `python3 summarize.py RAW_CARGO_DIR EXISTING_OUTPUT_DIR` checks the four fresh artifact receipts and matching outputs and counters without recompiling. The fixture includes no private user profiles.
