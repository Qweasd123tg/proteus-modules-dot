# Make model selection own configured fallback options

Standalone Core patch for `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify the packet with `sha256sum -c SHA256SUMS`; run `git apply --check source.patch` first. The same patch fits the verified Core stack through #964.

Move the existing model and reasoning-effort fallback helpers into model selection, their only caller. The configuration summary still consumes selection, but selection no longer imports the summary.

Configured model order, matching by exact physical route, active-profile priority, deduplication and trimming are unchanged. Discovery and failure behavior, catalog wire types, local configuration and persisted settings are unchanged. Tests exercise route selection, model/effort rejection and local configuration while a synthetic discovery request waits. See `receipt.json` for the exact trees and checks. No external provider or real tools run.
