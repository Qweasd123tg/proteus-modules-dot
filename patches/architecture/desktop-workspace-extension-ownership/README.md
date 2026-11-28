# Put shared UI surfaces and workspace events under Workspace

Standalone source patch for Desktop `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. Verify `sha256sum -c SHA256SUMS`; use `git apply --check source.patch` before applying it to the corresponding Desktop checkout. This patch also applies after the verified Desktop patch stack through #953.

Workspace owns the existing view/focus/rehost tuple, preview/focus options and event emitter. Terminal, project navigation, notifications and subagent surfaces no longer import the extension module merely for these types. Extension Host consumes the Workspace types rather than declaring them.

This removes a direct source dependency, not actual extension routing through tabs, panels and chats. Extensions remain separately installable. No shared abstraction, IPC change, view lifecycle change or permission change is introduced. The test scope and exact source trees are in `receipt.json`.
