# Core: release the profile comparison clone before awaiting refresh

During a semantic profile-watch check, Core clones the current config, then serializes and compares it to the observed fingerprint. The clone is now scoped to that comparison and released before the poll loop can await a refresh or clear a profile error. The read guard still ends at the same clone statement, before serialization. The serializer, error fallback, comparison and short-circuit order, and all refresh, cancellation and publication branches are unchanged.

This shortens the lifetime of an owned temporary config. It does not remove the clone, change the live config, or measure app startup, idle memory, or process memory.

## Exact offline check

Use the unmodified file from `Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`, installed Linux x86-64 Rust 1.95.0, and an existing private scratch directory:

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py \
  --stock /path/to/Proteus-core/crates/proteus-core/src/app_server/profile_watch.rs \
  --rustc /absolute/path/to/rustc \
  --work-dir /path/to/private-scratch
```

The proof checks exact forward and reverse patch replay and lifts both native Rust comparison branches with inert lock, serializer, and async operation adapters. Seven tests pass in each of debug and optimized builds. Both arms drop the guard before serialization and return the same decisions and error reports. The stock clone survives the modeled pending awaits; the candidate drops it before those awaits. Tests also cancel the modeled refresh and drop the suspended futures on both paths. No real watcher, Tokio or Serde integration, or full Core build ran.
