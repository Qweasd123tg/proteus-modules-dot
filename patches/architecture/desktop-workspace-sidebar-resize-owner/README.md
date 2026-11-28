# Let Workspace own the shared sidebar resize

Keep the resize gesture and the logical width operations with Workspace,
which already holds the in-progress state. Chat panels and Settings still
compose their existing resize seams; Settings no longer imports a gesture
type from Panels. Preserve layout, gesture wiring, bounds, and persistence.

Use source.patch on the pinned Desktop revision, or source-after-stack.patch
on the cumulative tree in the receipt. The focused native checks cover
logical versus displayed width, commit/reset, preferences and layout.
