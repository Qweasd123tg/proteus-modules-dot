# Remove the SDK's Host-to-UI facade dependency

Move existing Node, SharedColumn, row, text and button definitions to one
private module. The public `proteus_extension::ui` paths re-export the same
definitions, and the Host imports them directly. Host-backed widget
composition is unchanged, including frame order and shared ownership.

`source.patch` applies to the pinned Extensions upstream.
`source-after-stack.patch` applies to the cumulative tree in the receipt. The SDK was compiled on each base
and five exact in-memory tests passed on each base without network or a
child process.
