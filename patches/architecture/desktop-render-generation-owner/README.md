# Make render generations a UI primitive

Standalone Desktop patch for `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify the packet with `sha256sum -c SHA256SUMS`. Apply **only one** alternative in the Desktop checkout:

- `source.patch` on the stock commit.
- `source-after-stack.patch` on the verified Desktop stack through #962 (tree `3ab71021c8f50a925799a438c9b7c1598e1143f6`).

Run `git apply --check` with the selected patch. Preferences, extension invalidation and chat measurement now share an existing render-generation primitive in the UI layer. Preferences no longer depend on Extensions for it; Extensions still read preferences. Extension-specific layout fingerprints remain in Extensions.

App and window generation rules, registration, cross-window uniqueness and all invalidation points are unchanged. The extension protocol does not change. See `receipt.json` for exact source and native checks with synthetic GPUI fixtures; no external provider or real extension process.
