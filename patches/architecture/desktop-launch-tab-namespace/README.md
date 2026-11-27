# Pass only a layout owner to Desktop preferences

Standalone Desktop patch on `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS`, then run `git apply --check /absolute/path/to/source.patch` in a detached Desktop checkout.

Launching can consult preferences. Preferences and window persistence don't need to know about launch targets. Pass them the layout namespace (canonical workspace and exact optional profile), derived by the existing launch layer, instead of the entire target. Restore and persistence in the new window now share one resolved owner.

Attach still yields no owner, unlike a default local profile. No connection settings are passed to preferences. Explicit picker, fresh start, preference fallback and profile matching remain intact. No serialized schema, Core wire protocol, backend selection or extension contract changes. See the receipt for exact verification.
