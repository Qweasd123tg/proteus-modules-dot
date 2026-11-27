# Share Desktop device-path resolution without depending on preferences

Standalone Desktop patch on `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` to a detached Desktop checkout. It also applies after #947.

Desktop preferences, catalog, extension discovery, themes, visual settings and the layout cache use the same config-dir resolver. Move the resolver from preferences to a small path leaf and delete the identical resolver in the layout cache. Absolute XDG precedence, HOME fallback, directory names and file creation points are unchanged. Bundled extensions, Core configuration and the cache root remain separate.

This removes the direct catalog-to-preferences path dependency. The indirect manifest-to-preferences badge type dependency remains. No changes to Core, wire contracts, package install semantics or stored settings. See receipt.json for exact source trees and test evidence.
