# Keep extension badge placement independent of preferences

Standalone Desktop patch on `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` to a detached checkout (also checked after #947 and #948).

Manifest parsing and preference overrides now share the same declaration-side badge placement type. Only placement data moved; saved override/order policy stays in preferences. The seven JSON names, omitted-place default, visible order and narrow rail requirement are unchanged.

Together with #948 this removes the analyzed catalog/manifest reverse path to preferences, not all Desktop module cycles. No change to installed packages, manifest or preference JSON, network or Core wire protocol. See receipt.json for exact Git and native test evidence.
