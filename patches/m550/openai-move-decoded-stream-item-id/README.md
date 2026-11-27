# Move a decoded item ID in OpenAI Responses text deltas

An explicit string item ID already belongs to the parsed event. Move it
into the existing text/refusal stream state instead of making a second
copy. The output-index fallback, empty explicit ID, event matching,
message phase/order, refusal finalization and tool handling do not change.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. An offline optimized translation
probe measured one fewer fresh Rust request per event for both the
40-byte and 4096-byte nonempty explicit ID, equal to their decoded size.
Empty, absent, null and numeric controls and reallocation counts were
unchanged. All 38 selected tests passed on each arm (36 existing, two
synthetic); both exact production libraries compiled without overlays.

Use source.patch on the exact base. The receipt includes reversible
source-only after-#847/#848 and M650 alternates. No live provider, latency
or end-to-end memory claim.
