# Avoid copying tool argument schemas for settings

Tool argument schemas are not part of the Settings DTO. Skip copying them
in that private view, keeping the full public diagnostic graph and schema,
the executable inventory and module configuration schemas unchanged.

Apply **one** selector. Use `source.patch` on exact stock Core
`024fb944a91382026bb2aa5c7b8da65c284d0305` without #932. Use `after-dot932.patch` if #932
is already applied, preserving its graph optimization. Do not apply both.

Native release tests passed on both selectors: 146 and 146 per arm.
Full public and Settings JSON are byte-identical on 0/8/128 tool fixtures.
The 8-tool fixture with rich schemas saves 1720 requests and
141,160 requested bytes; the zero-tool control is unchanged.
These are topology projection counters, not whole-app PSS.
