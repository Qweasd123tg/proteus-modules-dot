# Storage SDK: reuse the owned Base64 reply

Successful `ReadBlob` and `ReadBlobByHash` responses already own the Base64 string. The session-storage SDK currently copies it while converting the typed response into a JSON value. This standalone patch reuses a nonempty string only if its capacity exactly equals its length. Serde still writes the existing response structure and field order. Empty strings, spare-capacity strings, unexpected serialization and other responses retain the old behavior. Validation, blob I/O and hashing, transport, limits and the public contract are unchanged.

The only production change is `source.patch` against the worker's locked [Core 0c1b7572](https://github.com/Proteus-harness/Proteus-core/tree/0c1b7572313230e5d123e95c722e1258a2e9ecd6) in `crates/proteus-module-sdk/src/session_storage.rs`. The real worker comes from [Modules 331cfc20](https://github.com/Proteus-harness/Proteus-modules/tree/331cfc20bbaf821ab07de49868426da29ebdeb64). The checked current [Core b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14) has the same export blob. The remote session store used by the host's `/image` route calls `ReadBlobByHash`; this package does not exercise that HTTP route or claim a change to local image reads, startup, or process RAM.

## Evidence

- Fresh native release workers: stock and candidate, both JSONL/SQLite and both `serde_json` map modes. In 132 paired scenarios, stdout bytes or rejection behavior matched, including a frame exactly 8,388,608 bytes and its one-byte overflow, another explicit exact limit, a valid 5 MiB image, and a 64 MiB blob under the 128 MiB frame cap. The unmodified worker process suite passed 2/2 for each of four builds. See `frames-default.json`, `frames-preserve_order.json`, and `native-builds.json`.
- In the instrumented default-map workers reading the 5 MiB image, the SDK conversion peak for Rust allocations of at least 64 KiB fell from **13,981,016 to 6,990,508 bytes**. One 6,990,508-byte allocation disappeared. The live payload was unchanged during real Linux pipe backpressure, including four held responses (27,962,032 bytes in total), and zero remained after drop. The full measured span **did not improve**: the earlier read-and-encode peak remained 15,379,116 bytes per invocation in both arms. These are allocation measurements, not RSS or PSS. See `native-meter.json` and `meter-builds.json`.
- In both map modes, the SDK release unit suite passed 5/5 stock and 6/6 candidate, including forced fallback, arbitrary producers with excess capacity, and a paused flush. See `sdk-verification.json`.

## Replay

Use Python 3.11+, Git, Linux x86-64 Rust/Cargo 1.95.0, a C toolchain, the two checked source trees, and the checksum-pinned crate archives. The verified projected lock is local to the isolated proof; it does not change either upstream lock.

```sh
sha256sum -c SHA256SUMS
python3 -B replay_worker.py --modules /path/to/modules --core /path/to/locked/core \
  --toolchain-bin /path/to/rust/bin --archives /path/to/official/crate-archives --work /fresh/work
```

Then use [NATIVE-PROOF.md](NATIVE-PROOF.md) for the live protocol and allocator replay, and [SDK-PROOF.md](SDK-PROOF.md) for the SDK-specific controls. Only the pinned native workers and focused suites were tested, not the full upstream monorepos.
