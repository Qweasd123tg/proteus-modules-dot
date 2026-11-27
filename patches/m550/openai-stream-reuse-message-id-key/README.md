# Look up existing OpenAI Responses message IDs without cloning their keys

Known text and refusal item IDs borrow their existing keys on lookup.
New item IDs only clone the key at insertion, with the same generated ID
and stream bookkeeping. The cold miss may do a second hash lookup if
the map is already populated. No timing claim.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. Offline optimized translation: one
fewer allocation on a hit for each nonempty key (40- and 4096-byte
explicit IDs and 8-byte output-index fallback). The empty explicit ID
and all cold miss allocation counts were unchanged; IDs, phases and
refusal controls matched. All 39 selected tests passed on each arm
(36 existing, three synthetic); exact unmasked libraries compile.

Use source.patch on the exact base. The receipt includes exact reversible
source-only alternates for #847/#848, #895 and M650 with or without #895/#896. No live provider,
latency, app PSS or full-suite claim.
