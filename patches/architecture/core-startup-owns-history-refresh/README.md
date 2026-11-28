# Core: keep startup history refresh orchestration in startup

Base: `Proteus-harness/Proteus-core@550603155239238fdf73777d53d77f327d1e7a71`.

The session read-model module now projects the display from a store and already validated journal read. App-server startup owns refreshing the cached resume and publishing the replacement history. The same projection can still persist the cache. No changes to when the baseline is captured, task and blocking projection order, comparison against the baseline, journal writes, error propagation, or event payloads. The event-owned DTO in the cumulative variant stays where #988 put it. No new primitive or module API.

Choose *one* variant: `source.patch` for exact main, or `source-after-stack.patch` for the verified overlay tree `9ecf35eabd9d9fc5d0d4c177a53f2e368c141eaf` (includes #988). Use `git apply --check` with the chosen file before applying. Verify packet files with `sha256sum -c SHA256SUMS`.

The receipt covers both trees and three native tests per tree: stale startup snapshot recovered from a synthetic journal without a turn, a late update that must not overwrite the new active turn, and snapshot replacement after reconnect. The synthetic startup case uses preverified local storage/reference fixtures and no real model or tools.
