# Project only the settings needed by Add-ons

The Add-ons snapshot only returns configured add-ons and configured MCP
servers from the profile. Build that existing typed value directly from
the already selected assembly. Discovery order, registry statuses, profile
reload errors and writeability are unchanged.

Exact Core `7f86a85b0b45de62c08ca36f21244afc03e6101e`. 53 targeted release tests passed per arm.
The HTTP suite covers a local fixture with skills, plugins, MCP state and
config persistence. The warm allocation control uses no active model,
plugin, context provider or MCP server. The entire ordered snapshot is
byte-identical across both arms for all three instruction sizes.
Without additional instructions it saves 10 allocator
requests and 4,850 cumulative requested bytes per snapshot.
The 64 KiB control saves 70,442 cumulative bytes.
This is not a PSS or startup measurement. Strict apply and reversal also
pass with the preceding compatibility stack.
