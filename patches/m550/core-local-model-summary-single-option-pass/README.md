# Build configured model choices once for the local summary

The local snapshot builds configured models once and separates the
active provider's selector from the other provider groups. Discovery
retains its original requests, deadline, ordering and error behavior.

Apply **one** selector. Use `source.patch` on exact stock Core
`024fb944a91382026bb2aa5c7b8da65c284d0305` without #927. Use `after-dot927.patch` if #927 was
already applied, preserving its borrowed config. Do not apply both.

Native release tests passed on both selectors: 103 per arm on the
standalone base and 104 per arm after #927. Exact local summaries match
after masking the temporary paths. The 16-alias fixture saves
46 allocation requests standalone and 46 after #927.
These are isolated local-summary counters, not device RAM or startup.
