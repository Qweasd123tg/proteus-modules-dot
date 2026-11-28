# Let Desktop Chats own session projection

Standalone proposal for Desktop commit `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Check the packet with `sha256sum -c SHA256SUMS`. Apply **only one** of these alternatives in the Desktop checkout:

- `source.patch` on the upstream commit.
- `source-after-stack.patch` after the verified Desktop patches through #960, on tree `d00685c7e356f046ec331e4e53ce66f4c7eba33d`. It preserves the Workspace ownership changes from #958.

Run `git apply --check` with the selected patch before applying it. Both variants were checked forward and in reverse against their exact trees.

Chats owns the session event it publishes and the projection used by Extensions for snapshots and updates. The projection file is byte-identical, and the public wire types stay in `declarative/session.rs`. This removes Chats’ dependency on Extensions for projection; together with #958, it clears direct Extension module references from the Chats producer. It does not remove extension integration from other UI code.

Active/retained session selection, Core-chat checks, scope and directory filtering, event IDs, deduplication, and snapshot/update formats are unchanged. No modules or extensions need rebuilding for a new protocol. See `receipt.json` for the native test groups on both trees. The tests cover synthetic transcript projection, reconnect routing, scope restrictions, bootstrap order and deduplication; they do not exercise a live Core or a real extension process.
