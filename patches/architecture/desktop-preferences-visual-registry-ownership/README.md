# Let Preferences own the saved visual registry

Standalone Desktop patch for `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS`; run `git apply --check source.patch` in the corresponding Desktop checkout before applying. The patch also applies after the verified Desktop stack through #959.

Preferences owns the existing saved registry and validates its absolute paths without consulting Visual Config. Visual Config still owns document selection, canonical/alias checks, loading, and saving. There is no new registry or intermediary. The saved JSON keys, tolerance of unavailable absolute paths, and per-window extension and appearance choices stay the same.

See `receipt.json` for the tested tree, native tests, settings migration tests and exact evidence hashes. Core, package and wire contracts were not changed.
