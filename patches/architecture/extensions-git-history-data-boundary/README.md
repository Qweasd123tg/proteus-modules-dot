# Extensions: separate Git log data from history rendering and fetching

Base: `Proteus-harness/Proteus-desktop-extensions@d123bc70c83522b5328a414cdcad1ac6676464b8`.

Move the existing parsed page, entry and fallback summary to a private data module. Main state and history no longer own each other's record types, and a commit document can read its summary without importing the mixed history module. Fetching, layout, row ordering, malformed row handling, UI primitives, commands, the manifest and the SDK remain unchanged.

Verify with `sha256sum -c SHA256SUMS` and `git apply --check source.patch` in the Extensions checkout. This one patch was verified on exact main and the cumulative SDK/Plan overlay. Four native tests per base use in-memory log data only; no Git or extension server was run.
