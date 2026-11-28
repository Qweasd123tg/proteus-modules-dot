# Desktop: separate catalog index loading from skill discovery

Base: `Proteus-harness/Proteus-desktop@b93833f5043d1c2f10bb6c40638587f56e591ffc`.

Catalog composition decides whether to read the explicit index or discover agent skills. The index schema no longer imports the discovery implementation. Listing and document preview share only the pure Markdown frontmatter splitter. The explicit index still takes precedence whenever present; a malformed index still returns its own error. The separate discovery and preview bounds, file and path checks, and Git refresh sequence remain unchanged. No package, install, runtime, or wire contract change.

Apply from the Desktop checkout with `git apply --check source.patch`, then `git apply source.patch`. Verify packet files with `sha256sum -c SHA256SUMS`. The same patch was checked strictly in both directions on the exact Desktop main tree and on its cumulative architecture overlay. The receipt identifies focused headless tests; no git subprocess, live tools, or installations were used by those fixtures.
