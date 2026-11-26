# Reuse the validated catalog on a successful OpenCode Go refresh

The native OpenCode Go adapter already builds and validates a typed catalog
before accepting a live refresh. Keep that transient result and return it
instead of cloning the identical selection again from the new Models.
No new retained cache. Offline seed, warm/fallback result, filtering/order,
validation, 300-second success interval, 15-second retry interval, locking and
HTTP behavior are unchanged.

Apply to Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`. None of the
verified selectors through #828 overlap the exact paths.

Both unmasked production libraries compiled with pinned native Rust and
dependencies. Seven focused native Go tests passed per arm (private test
overlay; no full crate or broker suite). Using the real native adapter with an
owned loopback HTTP server, successful cold refresh built two catalog
projections in stock and one in the candidate. Warm, failed refresh and
cooldown each still built one. Go preserved the last good catalog on HTTP
failure, and the success/retry deadline controls passed. The loopback checks
show served requests, not all possible failed connection attempts. No real
account/provider traffic, whole-application timing or memory claim.
