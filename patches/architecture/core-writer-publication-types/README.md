# Keep writer and display publication coordinated by the session store

Both patches deliver the same ownership change. Apply only one:
- `source.patch` applies to untouched Core `024fb944a91382026bb2aa5c7b8da65c284d0305`.
- `source-after-stack.patch` applies to Core after #943, #944, #946, #950 and #951, exact tree `6bd8e1e37ab58c21e843801ce81ba8f84c68b6bb`. The previous patch removed a neighboring import, so this variant has the corresponding context.

Verify `sha256sum -c SHA256SUMS` and `git apply --check /path/to/selected.patch` before applying.

The parent session store owns the existing shared handle registry and committed display data. The writer no longer imports the display layer. Pointer/locator identity, one shared runtime state, mutexes, writer lease/ack behavior, journal and display publication are unchanged. No wire or format change.

The receipt records native checks on the standalone patch and strict stacking, inverse and a separate native view test pass for the contextual patch.
