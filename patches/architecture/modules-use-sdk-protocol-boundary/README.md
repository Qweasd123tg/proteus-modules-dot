# Keep the Modules protocol dependency behind its existing SDK export

Standalone patch for Modules `7274147162cb226f05df13a52b4a271fa5619313`. Verify with `sha256sum -c SHA256SUMS`, then run `git apply --check source.patch`. The same patch fits the verified Modules stack through #963.

The common module runtime imports the existing protocol function through the same pinned SDK. The reference executable declares its own direct protocol and Serde dependencies only for tests, preserving the exact options. The normal transitive package sets, SDK pin, on-wire behavior and binding checks do not change.

See `receipt.json` for the direct dependency kinds, strict source checks, native worker checks and the compile-only integration target. The independently built context package and reference version entry points remain separate; no portable install or external provider was used.
