# Core: avoid unnecessary file checks in config diagnostics

For a config directory, the diagnostics helper now checks each child's extension before calling `Path::is_file`. Only exact lowercase `.toml` and `.json` names can qualify, as before. The same metadata check still follows symlinks for eligible names. An explicit file of any extension still qualifies and now moves its already-owned path instead of cloning it.

This preserves exact sorted paths, lexical aliases, inline reference handling, and the handling of scan failures. It does not change config loading, validation, monitoring, or permissions, and does not provide a snapshot of concurrently changing directories.

## Exact offline check

Use the two unmodified files from `Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`, installed Linux x86-64 Rust 1.95.0, and an existing private scratch directory:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock /path/to/Proteus-core/crates/proteus-core/src/core/config/files.rs \
  --reference /path/to/Proteus-core/crates/proteus-core/src/core/config/reference.rs \
  --rustc /absolute/path/to/rustc \
  --work-dir /path/to/private-scratch
```

The proof checks exact forward and reverse patch replay and compiles the complete before/after helper files with the exact `physical_config_path` implementation. Seven tests passed in each of debug and optimized builds on a synthetic filesystem. A separate instrumented copy counted 1,003 vs. three `Path::is_file` calls for 1,000 ineligible children and two eligible names, including one root check. It also confirmed that the explicit-file result reuses the physical path buffer. These are helper-level observations, not syscalls, app startup times, or process memory measurements.
