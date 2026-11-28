# Desktop: remove panels' dependency on window chrome

Base: `Proteus-harness/Proteus-desktop@dd51ad4af74756dacf5b2473a758a3109c1fce80`.

The workspace owns the same event it already emits. Folder labels come from the existing UI formatting module. This removes the two imports from panels back to the window chrome, while keeping chrome's normal use of the panels. Window composition, launch callbacks, event payloads, project routing and displayed folder names are unchanged.

Verify with `sha256sum -c SHA256SUMS`. Choose one variant: `source.patch` for exact main, or `source-after-stack.patch` for cumulative Desktop tree `095682ad088df3d7d41395c9b8656fd5206cf884`. Run `git apply --check` on the chosen patch before applying. The receipt records strict forward/inverse on stock and cumulative, plus four native tests per base with in-memory project and path fixtures; no real picker or app launch.
