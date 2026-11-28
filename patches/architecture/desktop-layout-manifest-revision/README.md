# Keep Desktop layout fingerprints consistent with their catalog snapshot

Standalone Desktop patch on `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS`, then check and apply `source.patch` from a detached checkout.

The immutable UI manifest now carries the source revision of the same Installed entry. The layout fingerprint reads ID and revision from one ordered, enabled catalog snapshot; it no longer re-reads the raw registry for each package. All enabled packages still count, including non-content providers.

The scalar-v3 tuple order, key encoding, scanner, package/visual invalidation, runtime and Core revision namespaces are unchanged. The existing build-commit salt remains, so cache hits across binaries are not promised. See receipt.json for verification.
