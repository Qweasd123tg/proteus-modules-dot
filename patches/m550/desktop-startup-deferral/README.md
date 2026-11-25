# Desktop: defer the second session list on startup fallback

When restore has neither a resumed Core chat nor a bootstrap suggestion, keep the initial session list and successful creation acknowledgement, but don't wait for another list before returning the boot result. The existing refresh runs after startup opens the chat. The first ordered snapshot is provisional; it doesn't invent a sidebar row. Initial list and creation failures stay startup failures. A late list failure is reported by the refresh without discarding the created chat.

A detached Rust comparison ran the lifted restore and refresh branches against a synthetic loopback peer. Holding the second list blocked stock boot; the candidate admitted boot with the exact created session and workspace before requesting the refresh. All 16 success, error and route control arms passed. The fixture substitutes the real API transport, UI shell and scheduling; it does not measure wall time, RAM, normal launch, or history rendering.

This one-hunk patch applies directly to current Desktop and composes with #684 in both orders.
