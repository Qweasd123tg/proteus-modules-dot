# Route Desktop renderers from one catalog snapshot

Standalone Desktop patch for `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` in a detached checkout.

Content language and format metadata now come from the same descriptors that determine enabled status and user order, rather than consulting the raw registry again for each candidate. Duplicate registrations, first winner and existing priorities are preserved.

The selected descriptor is checked against the current catalog at new mount admission. If an entry disappeared or was replaced before admission, existing plain/markdown/source fallback is used instead of attempting to mount it. Previously mounted views still use the normal reload path; this is not an OS-level package pin or a guarantee of atomicity for a whole frame. Core/preview capability scope, manifest schema and protocol are unchanged.

See receipt.json for exact source and native test evidence.
