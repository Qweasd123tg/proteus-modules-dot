# Extensions: keep plan rendering outside the plan model

Base: `Proteus-harness/Proteus-desktop-extensions@d123bc70c83522b5328a414cdcad1ac6676464b8`.

Model, cache and settings can work with plan data without the model importing widget construction. Move the existing details renderer and preview example verbatim into a private presentation module. The example and live details use the same helper and existing primitives, without changing preview lifecycle, row order, text, tones or icons. The manifest, SDK, package inputs and session/cache behavior are unchanged.

Verify the packet with `sha256sum -c SHA256SUMS`. Run `git apply --check source.patch` in the Extensions checkout, then apply the patch. The same patch was checked forward and backward on exact main and the established SDK overlay. Four native tests per base use local in-memory fixtures; no extension or tool was launched.
