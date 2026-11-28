# Let Settings own the shared configuration controls

Move the profile picker, its catalog, and appearance actions into the
existing Settings configuration module. The Launcher still uses the shared
controls at startup; Settings no longer reaches back into Launcher for them.
Rendering, settings changes and profile-opening callbacks keep their roles.

Use source.patch on pinned upstream or source-after-stack.patch on the
cumulative tree. Five native fixtures passed per base with synthetic local
profiles and UI state, without launching a real dialog or backend.
