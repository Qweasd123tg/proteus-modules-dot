# Validate only the selected module package payloads

Standalone Modules patch on `7274147162cb226f05df13a52b4a271fa5619313`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` in a detached Modules checkout.

The packager still checks the complete ID/requirements roster. In a selected build it reads the selected exports and model-preset payloads only. The full build, portable bundle without a selector, and source catalog still validate all package payloads. Cargo's workspace checks, selected package validation, SHA verification and installation/rollback are unchanged.

The actual CLI built and packaged session-storage on the pinned source with an invalid unrelated model preset in an isolated fixture. The stock CLI rejected that focused request; the new CLI still rejects the invalid package itself and rejects full validation. See receipt.json for exact verification.
